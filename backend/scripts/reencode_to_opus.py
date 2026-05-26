"""Reprocesa la biblioteca a Opus (.opus en contenedor Ogg).

Re-descarga cada pista desde su `source_url` de YouTube prefiriendo el stream
Opus y copiándolo sin recodificar (mínimo tamaño, máxima calidad). Sustituye el
fichero antiguo (m4a) por el nuevo .opus en la MISMA carpeta y actualiza la fila
del Track (file_path/format/size). NO usa el scanner para evitar duplicados.

Solo procesa pistas que tienen `source_url` (las descargadas de YouTube). Las que
no lo tienen (Spotify resuelto sin YouTube, subidas manuales) se informan y omiten:
re-buscarlas a ciegas arriesga bajar otra versión.

Uso:
    python -m scripts.reencode_to_opus --dry-run        # solo informa
    python -m scripts.reencode_to_opus --id 48          # una pista (prueba)
    python -m scripts.reencode_to_opus --limit 3        # las 3 primeras
    python -m scripts.reencode_to_opus                  # toda la biblioteca
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from sqlmodel import select

from app.config import settings
from app.db import session_scope
from app.models import Album, Artist, Track
from app.services import downloader, organizer
from app.services.spotify import TrackMeta

ALREADY_OK = {"opus", "ogg"}


def _collect() -> list[dict]:
    """Saca los datos planos de las pistas a convertir (sin mantener sesión abierta)."""
    items: list[dict] = []
    with session_scope() as s:
        for t in s.exec(select(Track)).all():
            fmt = (t.file_format or "").lower()
            artist = s.get(Artist, t.artist_id) if t.artist_id else None
            album = s.get(Album, t.album_id) if t.album_id else None
            album_artist = s.get(Artist, album.artist_id) if album and album.artist_id else None
            items.append(
                {
                    "id": t.id,
                    "file_path": t.file_path,
                    "source_url": t.source_url,
                    "fmt": fmt,
                    "title": t.title,
                    "artist": artist.name if artist else "Unknown Artist",
                    "album": album.title if album else "",
                    "album_artist": (album_artist.name if album_artist else (artist.name if artist else "")),
                    "year": album.year if album else None,
                    "track_number": t.track_number or 0,
                    "duration_ms": t.duration_ms or 0,
                }
            )
    return items


def _meta_for(it: dict) -> TrackMeta:
    return TrackMeta(
        spotify_id=f"reopus-{it['id']}",
        title=it["title"],
        artists=[it["artist"]],
        album=it["album"],
        album_artist=it["album_artist"],
        track_number=it["track_number"],
        disc_number=0,
        total_tracks=0,
        duration_ms=it["duration_ms"],
        isrc="",
        year=it["year"],
        cover_url=None,  # la carátula vive en covers/ aparte; no hace falta re-embeber
        source_url=it["source_url"] or "",
        source_kind="track",
    )


def _transcode_local(old_abs: Path) -> Path:
    """Transcodifica un fichero a Opus con ffmpeg (para pistas sin source_url).
    Pierde algo de calidad — ya eran lossy — pero ocupan menos y quedan en opus."""
    new_abs = old_abs.with_suffix(".opus")
    tmp = old_abs.parent / (old_abs.stem + ".__tmp__.opus")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(old_abs),
        "-vn", "-c:a", "libopus", "-b:a", "160k", "-map_metadata", "0",
        str(tmp),
    ]
    subprocess.run(cmd, check=True, timeout=300)
    tmp.replace(new_abs)
    return new_abs


def _update_track_file(tid: int, new_abs: Path) -> None:
    new_rel = str(new_abs.relative_to(settings.music_dir))
    size = new_abs.stat().st_size
    with session_scope() as s:
        t = s.get(Track, tid)
        if t:
            t.file_path = new_rel
            t.file_format = "opus"
            t.file_size = size
            s.add(t)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="solo informa, no toca nada")
    ap.add_argument("--id", type=int, default=None, help="procesar solo esta pista")
    ap.add_argument("--limit", type=int, default=None, help="máximo de pistas a procesar")
    ap.add_argument("--local", action="store_true",
                    help="además, transcodear localmente las pistas sin source_url")
    args = ap.parse_args()

    items = _collect()
    if args.id is not None:
        items = [i for i in items if i["id"] == args.id]

    todo = [i for i in items if i["fmt"] not in ALREADY_OK]
    no_src = [i for i in todo if not i["source_url"]]
    convertibles = [i for i in todo if i["source_url"]]
    if args.limit:
        convertibles = convertibles[: args.limit]

    print(f"Biblioteca: {len(items)} pistas en esta selección.")
    print(f"  ya en opus/ogg: {len(items) - len(todo)}")
    print(f"  a convertir (re-descarga, con source_url): {len(convertibles)}")
    accion = "transcode local" if args.local else "se omiten"
    print(f"  sin source_url ({accion}): {len(no_src)}")
    if no_src and not args.local:
        print("    →", ", ".join(str(i["id"]) for i in no_src))
    if args.dry_run:
        print("\n[dry-run] no se ha tocado nada.")
        return 0

    ok = 0
    failed: list[tuple[int, str]] = []
    for n, it in enumerate(convertibles, 1):
        tid = it["id"]
        old_abs = settings.music_dir / it["file_path"]
        print(f"\n[{n}/{len(convertibles)}] id={tid} · {it['title'][:50]!r}")
        if not old_abs.is_file():
            print(f"  ! fichero no encontrado: {old_abs} — omito")
            failed.append((tid, "fichero original ausente"))
            continue
        try:
            dl = downloader.download_with_ytdlp_direct(_meta_for(it))
            if not dl.success or not dl.file_path:
                print(f"  ! descarga falló: {dl.error}")
                failed.append((tid, dl.error or "download failed"))
                continue
            new_abs = old_abs.with_suffix(".opus")
            shutil.move(str(dl.file_path), str(new_abs))
            try:
                organizer.write_tags(new_abs, _meta_for(it))
            except Exception as e:  # noqa: BLE001
                print(f"  · aviso: write_tags falló: {e}")

            _update_track_file(tid, new_abs)
            size = new_abs.stat().st_size
            # Borra el m4a antiguo si quedó aparte
            if new_abs != old_abs and old_abs.exists():
                old_abs.unlink()
            print(f"  ✓ {old_abs.name} → {new_abs.name} ({size/1024:.0f} KB)")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ! error: {e}")
            failed.append((tid, str(e)[:200]))

    # ─── Transcode local de las que no tienen source_url (--local) ───
    if args.local:
        for n, it in enumerate(no_src, 1):
            tid = it["id"]
            old_abs = settings.music_dir / it["file_path"]
            print(f"\n[local {n}/{len(no_src)}] id={tid} · {it['title'][:50]!r}")
            if not old_abs.is_file():
                print(f"  ! fichero no encontrado: {old_abs} — omito")
                failed.append((tid, "fichero original ausente"))
                continue
            try:
                new_abs = _transcode_local(old_abs)
                _update_track_file(tid, new_abs)
                size = new_abs.stat().st_size
                if new_abs != old_abs and old_abs.exists():
                    old_abs.unlink()
                print(f"  ✓ {old_abs.name} → {new_abs.name} ({size/1024:.0f} KB, transcode)")
                ok += 1
            except Exception as e:  # noqa: BLE001
                print(f"  ! error: {e}")
                failed.append((tid, str(e)[:200]))

    omitidas = 0 if args.local else len(no_src)
    print(f"\nHecho. Convertidas: {ok} · fallidas: {len(failed)} · omitidas sin URL: {omitidas}")
    for tid, err in failed:
        print(f"  fallo id={tid}: {err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
