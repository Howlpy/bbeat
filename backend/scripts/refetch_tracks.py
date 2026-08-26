"""Vuelve a descargar pistas concretas conservando su ficha en la biblioteca.

Pensado para reparar las pistas cuyo audio no corresponde a la canción (ver
scripts/audit_source_match.py). No borra la fila del track: se reencola un
job y, como el organizador sobrescribe el destino y el scanner reindexa por
ruta, la pista conserva su id, sus álbumes, sus guardados y sus
reproducciones. Solo cambia el fichero de audio.

De Spotify se relee ÚNICAMENTE la duración: es el objetivo que usa el
buscador y la guardada en la BD es la del audio equivocado, así que
reutilizarla volvería a traer la canción incorrecta. El resto (artista,
álbum, año, número, título) se toma de la ficha guardada, porque de ello
depende la ruta final; si la ruta cambiara, el scanner crearía una pista
nueva y la vieja se quedaría con el audio malo. Antes de encolar nada se
comprueba que el job reproduce exactamente la ruta actual, y si no, se omite.

Uso:
    python -m scripts.refetch_tracks --ids 102,103,210
    python -m scripts.refetch_tracks --ids 102,103 --dry-run

Cuando ya sabes cual es el video bueno, se puede fijar y saltarse el buscador:

    python -m scripts.refetch_tracks --ids 103 --url https://youtu.be/awdYrvQboi8
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app.config import settings
from app.db import engine
from app.models import Artist, Job, Track
from app.services import jobs as jobs_svc
from app.services import organizer, spotify

SPOTIFY_TRACK_URL = "https://open.spotify.com/track/{}"


@dataclass
class _FixedMeta:
    """Sustituto de TrackMeta cuando la URL la da el usuario.

    Con --url no se consulta a Spotify, asi que no hay metadata que releer:
    solo hace falta el id (con prefijo ``yt:`` para que el descargador use la
    via directa en vez de buscar) y la propia URL.
    """
    spotify_id: str
    source_url: str
    duration_ms: int
    total_tracks: int
    cover_url: Optional[str]
    artists: list[str]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True, help="ids de track separados por coma")
    ap.add_argument("--dry-run", action="store_true", help="no crea jobs, solo informa")
    ap.add_argument(
        "--url",
        help="URL exacta de YouTube/SoundCloud a usar (un solo --ids). Se baja "
             "de ahi directamente, sin buscar: para cuando ya sabes cual es",
    )
    args = ap.parse_args()

    wanted = [int(x) for x in args.ids.split(",") if x.strip()]
    if args.url and len(wanted) != 1:
        ap.error("--url fija UNA pista concreta: pasa un solo id en --ids")
    created, skipped = [], []

    with Session(engine) as s:
        for tid in wanted:
            track = s.get(Track, tid)
            if not track:
                print(f"  #{tid}: no existe")
                skipped.append(tid)
                continue
            ext = track.external_id or ""
            if args.url:
                # Con URL explicita no hay nada que buscar ni que consultar a
                # Spotify: el usuario ya sabe cual es el video bueno.
                video_id = jobs_svc._yt_video_id(args.url)
                if not video_id:
                    print(f"  #{tid}: no reconozco un video de YouTube en {args.url}")
                    return 1
                meta = _FixedMeta(
                    spotify_id=f"yt:{video_id}",
                    source_url=args.url,
                    duration_ms=track.duration_ms or 0,
                    total_tracks=1,
                    cover_url=None,
                    artists=[],
                )
            elif not ext or ext.startswith(("yt:", "sc:")):
                # Sin id de Spotify no hay metadata fiable que rebuscar, y con
                # yt:/sc: la descarga es directa desde source_url, que es
                # justamente la URL equivocada que queremos evitar.
                print(f"  #{tid} {track.title}: sin id de Spotify ({ext or 'vacío'}), se omite")
                skipped.append(tid)
                continue

            else:
                try:
                    result = spotify.resolve_url(SPOTIFY_TRACK_URL.format(ext))
                except Exception as e:
                    print(f"  #{tid} {track.title}: Spotify falló ({str(e)[:80]})")
                    skipped.append(tid)
                    continue
                meta = result.tracks[0]

            # De Spotify solo interesa la DURACION: es el objetivo que usa el
            # buscador y la de la BD es la del audio equivocado. Todo lo demas
            # se toma de la ficha guardada, porque de ello depende la ruta
            # final del fichero: si cambia, el scanner crea una pista NUEVA en
            # vez de actualizar esta y la vieja se queda con el audio malo.
            album = track.album
            artist = s.get(Artist, track.artist_id)
            artist_name = artist.name if artist else ""
            album_artist = album.artist.name if (album and album.artist) else None

            # El artista de BUSQUEDA sale de Spotify, no de la ficha: en las
            # playlists multi-artista la pista queda guardada como "Various
            # Artists" y la consulta resultante ("Various Artists - Bando Boyz
            # Free") no encuentra nada. La ruta no se ve afectada porque
            # target_path usa album_artist, que se sigue tomando de la ficha.
            search_artists = list(meta.artists) or [artist_name]

            def build(aa: str, year) -> Job:
                return Job(
                    source_url=args.url or SPOTIFY_TRACK_URL.format(ext),
                    source_kind="track",
                    spotify_track_id=meta.spotify_id,
                    title=track.title,
                    artist=search_artists[0],
                    artists_csv=", ".join(search_artists),
                    album_artist=aa,
                    album=album.title if album else "",
                    track_number=track.track_number or 1,
                    disc_number=track.disc_number or 1,
                    total_tracks=meta.total_tracks,
                    duration_ms=meta.duration_ms,
                    year=year,
                    cover_url=meta.cover_url,
                    user_id=None,
                    target_album_id=track.album_id,
                    status="pending",
                )

            # La ruta actual no siempre se puede deducir de la ficha: hay
            # carpetas con el año del álbum y otras sin él (el año se rellenó
            # después de organizar), y unas usan el artista del álbum mientras
            # otras usan el de la pista. En vez de adivinar se prueban las
            # combinaciones y se acepta la que reproduce la ruta EXACTA. Si
            # ninguna lo hace se omite, para no acabar duplicando la ficha.
            suffix = Path(track.file_path).suffix
            current = (settings.music_dir / track.file_path).resolve()
            job = None
            for aa in [a for a in (album_artist, artist_name) if a]:
                for year in (album.year if album else None, None):
                    cand = build(aa, year)
                    got = organizer.target_path(
                        jobs_svc._load_meta_from_job(cand), suffix
                    )
                    if got.resolve() == current:
                        job = cand
                        break
                if job:
                    break
            if job is None:
                fallback = organizer.target_path(
                    jobs_svc._load_meta_from_job(build(album_artist or artist_name,
                                                       album.year if album else None)),
                    suffix,
                )
                print("        ruta no reproducible, se omite:")
                print(f"          actual:   {track.file_path}")
                print(f"          quedaria: {fallback.relative_to(settings.music_dir)}")
                skipped.append(tid)
                continue

            print(f"        -> rebuscar «{track.title}» de {search_artists[0]} "
                  f"({meta.duration_ms // 1000}s, antes {(track.duration_ms or 0) // 1000}s)")
            if args.dry_run:
                continue

            # El id de Spotify es unique en jobs: quitar el job viejo del track.
            # spotify_track_id es unique en jobs, y puede haber MAS DE UNO que
            # estorbe: el de la ingesta original (id de Spotify) y el de una
            # URL fijada antes o pegada a mano en la app (yt:). Hay que quitar
            # todos, no solo el primero, o el INSERT revienta.
            old_ids = {meta.spotify_id, ext} - {""}
            old_jobs = list(
                s.exec(select(Job).where(Job.spotify_track_id.in_(old_ids))).all()
            )
            if any(j.status in ("pending", "running") for j in old_jobs):
                print("        ya hay un job en curso, se omite")
                skipped.append(tid)
                continue
            for old_job in old_jobs:
                s.delete(old_job)
            if old_jobs:
                s.flush()

            s.add(job)
            created.append(tid)
        if not args.dry_run:
            s.commit()

    if created:
        jobs_svc.wake()
    print(f"\njobs creados: {len(created)}  ·  omitidos: {len(skipped)}")
    if skipped:
        print("omitidos: " + ", ".join(str(i) for i in skipped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
