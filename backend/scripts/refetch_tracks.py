"""Vuelve a descargar pistas concretas conservando su ficha en la biblioteca.

Pensado para reparar las pistas cuyo audio no corresponde a la canción (ver
scripts/audit_source_match.py). No borra la fila del track: se reencola un
job con metadata FRESCA de Spotify y, como el organizador sobrescribe el
destino y el scanner reindexa por ruta, la pista conserva su id, sus álbumes,
sus guardados y sus reproducciones. Solo cambia el fichero de audio.

Es importante releer la metadata de Spotify en vez de usar la de la BD: la
duración guardada es la del audio EQUIVOCADO, y el buscador la usa como
objetivo, así que reutilizarla volvería a traer la canción incorrecta.

Uso:
    python -m scripts.refetch_tracks --ids 102,103,210
    python -m scripts.refetch_tracks --ids 102,103 --dry-run
"""
from __future__ import annotations

import argparse

from sqlmodel import Session, select

from app.db import engine
from app.models import Artist, Job, Track
from app.services import jobs as jobs_svc
from app.services import spotify

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

            artist = s.get(Artist, track.artist_id)
            print(f"  #{tid} {artist.name if artist else '?'} — {track.title}")
            print(f"        -> rebuscar «{meta.title}» de {meta.primary_artist} "
                  f"({meta.duration_ms // 1000}s)")
            if args.dry_run:
                continue

            # El id de Spotify es unique en jobs: quitar el job viejo del track.
            old = s.exec(
                select(Job).where(Job.spotify_track_id == meta.spotify_id)
            ).first()
            if old:
                if old.status in ("pending", "running"):
                    print("        ya hay un job en curso, se omite")
                    skipped.append(tid)
                    continue
                s.delete(old)
                s.flush()

            s.add(
                Job(
                    source_url=meta.source_url or SPOTIFY_TRACK_URL.format(ext),
                    source_kind="track",
                    spotify_track_id=meta.spotify_id,
                    title=meta.title,
                    artist=meta.primary_artist,
                    artists_csv=", ".join(meta.artists),
                    album_artist=meta.album_artist,
                    album=track.album.title if track.album else meta.album,
                    track_number=track.track_number or meta.track_number,
                    disc_number=track.disc_number or meta.disc_number,
                    total_tracks=meta.total_tracks,
                    duration_ms=meta.duration_ms,
                    year=meta.year,
                    cover_url=meta.cover_url,
                    user_id=None,
                    target_album_id=track.album_id,
                    status="pending",
                )
            )
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
