"""Limpieza one-off: convierte los álbumes fantasma 'Unknown Album' en pistas
sueltas (album_id NULL), quitando el tag de álbum del fichero para que un futuro
escaneo NO los vuelva a crear, y borra los álbumes vacíos resultantes.

Uso:
    python -m scripts.cleanup_singles --dry-run   # solo informa
    python -m scripts.cleanup_singles             # aplica
"""
from __future__ import annotations

import sys

import mutagen
from sqlmodel import select

from app.config import settings
from app.db import session_scope
from app.models import Album, AlbumSave, AlbumTrack, Track
from app.services import library as lib


def _strip_album_tags(file_path: str) -> bool:
    fpath = settings.music_dir / file_path
    if not fpath.is_file():
        return False
    try:
        au = mutagen.File(fpath, easy=True)
        if au is None:
            return False
        changed = False
        for k in ("album", "albumartist", "tracknumber"):
            if k in au:
                del au[k]
                changed = True
        if changed:
            au.save()
        return changed
    except Exception as e:  # noqa: BLE001
        print(f"  ! no pude limpiar tags de {file_path}: {e}")
        return False


def run(dry_run: bool) -> None:
    with session_scope() as s:
        albums = s.exec(
            select(Album).where(Album.title_normalized == "unknown album")
        ).all()
        print(f"Álbumes 'Unknown Album' encontrados: {len(albums)}")
        converted = 0
        for a in albums:
            tracks = s.exec(select(Track).where(Track.album_id == a.id)).all()
            print(f"  álbum id={a.id} → {len(tracks)} pista(s) a sueltas")
            if dry_run:
                continue
            for t in tracks:
                _strip_album_tags(t.file_path)
                t.album_id = None
                s.add(t)
                converted += 1
            # Quitar filas M:N y saves que apuntan a este álbum, luego borrarlo.
            for at in s.exec(select(AlbumTrack).where(AlbumTrack.album_id == a.id)).all():
                s.delete(at)
            for sv in s.exec(select(AlbumSave).where(AlbumSave.album_id == a.id)).all():
                s.delete(sv)
            lib._delete_album_record(s, a.id)
        if dry_run:
            print("DRY-RUN: no se ha cambiado nada.")
        else:
            print(f"Hecho: {converted} pistas a sueltas, {len(albums)} álbumes borrados.")
        if dry_run:
            s.rollback()


if __name__ == "__main__":
    run("--dry-run" in sys.argv)
