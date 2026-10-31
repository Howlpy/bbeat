"""Calienta la caché de letras (lyrics_cache) para toda la biblioteca.

Solo rellena la caché: no toca pistas ni ficheros. Salta las pistas ya cacheadas
(aciertos, o negativos aún vigentes); las que fallan por error de LRCLIB se
reintentan en la siguiente ejecución. Ritmo educado: 1 petición/s.

Uso:
    python -m scripts.prefetch_lyrics --limit 50
    python -m scripts.prefetch_lyrics            # toda la biblioteca
    docker exec bbeat python -m scripts.prefetch_lyrics --limit 500
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime

from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import Album, Artist, LyricsCache, Track
from app.services import lyrics as L


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="máx. de pistas a consultar (0 = todas)")
    ap.add_argument("--rate", type=float, default=1.0, help="segundos entre peticiones")
    args = ap.parse_args()

    init_db()
    done = found = errors = 0
    with Session(engine) as s:
        cache = {c.track_id: c for c in s.exec(select(LyricsCache)).all()}
        tracks = s.exec(select(Track).order_by(Track.id)).all()
        now = datetime.utcnow()
        for t in tracks:
            c = cache.get(t.id)
            if c and (c.found or now - c.fetched_at < L.NEGATIVE_TTL):
                continue
            if args.limit and done >= args.limit:
                break
            artist = s.get(Artist, t.artist_id)
            album = s.get(Album, t.album_id) if t.album_id else None
            real_album = (
                album.title
                if album and (album.kind or "album") == "album" and album.artist_id == t.artist_id
                else None
            )
            res = L.lookup(
                s, t.id, artist.name if artist else "", t.title, real_album,
                (t.duration_ms or 0) // 1000,
            )
            done += 1
            if res.get("error"):
                errors += 1
                estado = "ERROR"
            elif res.get("found"):
                found += 1
                estado = "OK"
            else:
                estado = "sin letra"
            print(f"[{done}] #{t.id} {t.title!r}: {estado}", flush=True)
            time.sleep(args.rate)
    print(f"consultadas={done} con_letra={found} errores={errors}")


if __name__ == "__main__":
    main()
