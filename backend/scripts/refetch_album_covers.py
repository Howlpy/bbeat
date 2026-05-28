"""Refetchea la carátula REAL por pista de un álbum/playlist.

Las playlists de Spotify resuelven sin portada por pista, así que todas las
canciones acababan con la portada de la playlist. Este script pide a Spotify la
portada de cada pista por su `external_id` y la guarda como carátula propia.

Solo toca pistas con external_id de Spotify (sin prefijo yt:/sc:); las demás
(YouTube/SoundCloud) ya tienen su miniatura y se dejan como están.

Uso:  python -m scripts.refetch_album_covers [album_id]            (dry-run)
      python -m scripts.refetch_album_covers [album_id] --apply
"""
from __future__ import annotations

import sys

from sqlmodel import select

from app.db import session_scope
from app.models import AlbumTrack, Track
from app.services import organizer, scanner, spotify

DRY = "--apply" not in sys.argv
ARGS = [a for a in sys.argv[1:] if not a.startswith("-")]
ALBUM_ID = int(ARGS[0]) if ARGS else 33  # ZorjMix por defecto


def main() -> None:
    print(f"=== refetch_album_covers album={ALBUM_ID} ({'DRY-RUN' if DRY else 'APPLY'}) ===")
    with session_scope() as s:
        rows = s.exec(
            select(Track.id, Track.external_id, Track.title)
            .join(AlbumTrack, AlbumTrack.track_id == Track.id)
            .where(AlbumTrack.album_id == ALBUM_ID)
        ).all()
    ok = skipped = failed = 0
    for tid, ext, title in rows:
        ext = ext or ""
        if not ext or ext.startswith(("yt:", "sc:")):
            skipped += 1
            continue
        try:
            cover_url = spotify.fetch_track_meta(ext).cover_url
        except Exception as e:
            print(f"  track {tid} '{title}': fallo resolver ({str(e)[:60]})")
            failed += 1
            continue
        if not cover_url:
            print(f"  track {tid} '{title}': sin cover_url")
            failed += 1
            continue
        print(f"  track {tid} '{title}' ← {cover_url[:60]}")
        if DRY:
            ok += 1
            continue
        data = organizer._fetch_cover_bytes(cover_url)
        if not data:
            print("    no se pudo bajar la imagen")
            failed += 1
            continue
        if scanner.save_track_cover(tid, data):
            with session_scope() as s:
                tr = s.get(Track, tid)
                if tr and not tr.has_cover:
                    tr.has_cover = True
                    s.add(tr)
            ok += 1
        else:
            failed += 1
    print(f"=== ok={ok} saltadas(no-spotify)={skipped} fallidas={failed} ===")


if __name__ == "__main__":
    main()
