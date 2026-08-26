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
"""
from __future__ import annotations

import argparse

from pathlib import Path

from sqlmodel import Session, select

from app.config import settings
from app.db import engine
from app.models import Artist, Job, Track
from app.services import jobs as jobs_svc
from app.services import organizer, spotify

SPOTIFY_TRACK_URL = "https://open.spotify.com/track/{}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True, help="ids de track separados por coma")
    ap.add_argument("--dry-run", action="store_true", help="no crea jobs, solo informa")
    args = ap.parse_args()

    wanted = [int(x) for x in args.ids.split(",") if x.strip()]
    created, skipped = [], []

    with Session(engine) as s:
        for tid in wanted:
            track = s.get(Track, tid)
            if not track:
                print(f"  #{tid}: no existe")
                skipped.append(tid)
                continue
            ext = track.external_id or ""
            if not ext or ext.startswith(("yt:", "sc:")):
                # Sin id de Spotify no hay metadata fiable que rebuscar, y con
                # yt:/sc: la descarga es directa desde source_url, que es
                # justamente la URL equivocada que queremos evitar.
                print(f"  #{tid} {track.title}: sin id de Spotify ({ext or 'vacío'}), se omite")
                skipped.append(tid)
                continue

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
            album_artist = album.artist.name if (album and album.artist) else None
            artist = s.get(Artist, track.artist_id)
            artist_name = artist.name if artist else ""
            job = Job(
                source_url=SPOTIFY_TRACK_URL.format(ext),
                source_kind="track",
                spotify_track_id=meta.spotify_id,
                title=track.title,
                artist=artist_name,
                artists_csv=artist_name,
                album_artist=album_artist or artist_name,
                album=album.title if album else "",
                track_number=track.track_number or 1,
                disc_number=track.disc_number or 1,
                total_tracks=meta.total_tracks,
                duration_ms=meta.duration_ms,
                year=album.year if album else None,
                cover_url=meta.cover_url,
                user_id=None,
                target_album_id=track.album_id,
                status="pending",
            )

            # Comprobacion dura: el job debe reproducir EXACTAMENTE la ruta
            # actual. Si no, se omite en vez de arriesgarse a duplicar la ficha.
            suffix = Path(track.file_path).suffix
            expected = organizer.target_path(jobs_svc._load_meta_from_job(job), suffix)
            current = settings.music_dir / track.file_path
            if expected.resolve() != current.resolve():
                print("        ruta no coincide, se omite:")
                print(f"          actual:   {track.file_path}")
                print(f"          quedaria: {expected.relative_to(settings.music_dir)}")
                skipped.append(tid)
                continue

            print(f"        -> rebuscar «{track.title}» de {artist_name} "
                  f"({meta.duration_ms // 1000}s, antes {(track.duration_ms or 0) // 1000}s)")
            if args.dry_run:
                continue

            # El id de Spotify es unique en jobs: quitar el job viejo del track.
            old_job = s.exec(
                select(Job).where(Job.spotify_track_id == meta.spotify_id)
            ).first()
            if old_job:
                if old_job.status in ("pending", "running"):
                    print("        ya hay un job en curso, se omite")
                    skipped.append(tid)
                    continue
                s.delete(old_job)
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
