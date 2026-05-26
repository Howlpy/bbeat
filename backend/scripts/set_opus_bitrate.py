"""Recodifica toda la biblioteca a Opus a un bitrate dado, IN SITU.

Útil para bajar el tamaño de las descargas offline (p. ej. 160k → 96k).
Recodifica con ffmpeg cada fichero a Opus al bitrate pedido, sustituye el
original (mismo path/extensión) y actualiza file_size. Ojo: re-encodear opus→opus
pierde un pelín; bajar de bitrate es una decisión consciente de tamaño/calidad.

Uso:
    python -m scripts.set_opus_bitrate --bitrate 96 --dry-run
    python -m scripts.set_opus_bitrate --bitrate 96
    python -m scripts.set_opus_bitrate --bitrate 96 --id 48
"""
from __future__ import annotations

import argparse
import subprocess
import sys

from sqlmodel import select

from app.config import settings
from app.db import session_scope
from app.models import Track


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bitrate", type=int, default=96, help="bitrate Opus en kbps")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--id", type=int, default=None, help="solo esta pista")
    args = ap.parse_args()

    with session_scope() as s:
        items = [
            (t.id, t.file_path)
            for t in s.exec(select(Track)).all()
            if args.id is None or t.id == args.id
        ]

    print(f"{len(items)} pistas a recodificar a Opus {args.bitrate}k")
    if args.dry_run:
        print("[dry-run] nada tocado.")
        return 0

    ok = 0
    failed: list[int] = []
    before = after = 0
    for n, (tid, fp) in enumerate(items, 1):
        src = settings.music_dir / fp
        if not src.is_file():
            print(f"  ! id={tid} fichero ausente: {fp}")
            failed.append(tid)
            continue
        tmp = src.parent / (src.stem + ".__rebr__.opus")
        try:
            bsz = src.stat().st_size
            subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
                 "-vn", "-c:a", "libopus", "-b:a", f"{args.bitrate}k", "-map_metadata", "0", str(tmp)],
                check=True, timeout=300,
            )
            tmp.replace(src)
            asz = src.stat().st_size
            before += bsz
            after += asz
            with session_scope() as s:
                t = s.get(Track, tid)
                if t:
                    t.file_size = asz
                    s.add(t)
            print(f"  [{n}/{len(items)}] id={tid}  {bsz // 1024}→{asz // 1024} KB")
            ok += 1
        except Exception as e:  # noqa: BLE001
            if tmp.exists():
                tmp.unlink()
            print(f"  ! id={tid} error: {e}")
            failed.append(tid)

    print(f"\nHecho: {ok} ok · {len(failed)} fallos · total {before/1e6:.0f} → {after/1e6:.0f} MB")
    if failed:
        print("  fallos:", failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
