"""Fusiona los álbumes fragmentados con un mismo título (una playlist importada
antes del arreglo del punto 4) en UNA sola playlist multi-artista.

Cada pista conserva su artista real; el álbum pasa a (TÍTULO / Various Artists)
con kind=playlist, owned por el dueño más común de los fragmentos y guardado para
él. Reescribe el tag albumartist de los ficheros (→ Various Artists) para que el
agrupado sea durable ante un futuro reescaneo. Borra los fragmentos.

Uso:
    python -m scripts.merge_makina --dry-run [TITULO]
    python -m scripts.merge_makina           [TITULO]   # aplica (def: makina)
"""
from __future__ import annotations

import shutil
import sys

import mutagen
from sqlmodel import select

from app.config import settings
from app.db import session_scope
from app.models import Album, AlbumSave, AlbumTrack, Artist, Track
from app.services import library as lib


def run(title_norm: str, dry_run: bool) -> None:
    with session_scope() as s:
        frags = s.exec(select(Album).where(Album.title_normalized == title_norm)).all()
        print(f"Fragmentos '{title_norm}': {len(frags)} (ids {[a.id for a in frags]})")
        if len(frags) < 2:
            print("Menos de 2 fragmentos: nada que fusionar.")
            return

        owners = [a.owner_id for a in frags if a.owner_id]
        owner_id = max(set(owners), key=owners.count) if owners else None
        title_display = frags[0].title
        year = next((a.year for a in frags if a.year), None)
        cover_src = next((a.cover_path for a in frags if a.cover_path), None)

        # Pistas afectadas (primarias + vía M:N)
        tids: set[int] = set()
        for a in frags:
            for t in s.exec(select(Track).where(Track.album_id == a.id)).all():
                tids.add(t.id)
            for r in s.exec(select(AlbumTrack.track_id).where(AlbumTrack.album_id == a.id)).all():
                tids.add(r[0] if isinstance(r, (tuple, list)) else r)

        if dry_run:
            print(f"  DRY: {len(tids)} pistas → 1 playlist '{title_display}' (owner {owner_id}); "
                  f"se borrarían {len(frags)} fragmentos.")
            s.rollback()
            return

        # Artista Various Artists
        va = s.exec(select(Artist).where(Artist.name_normalized == "various artists")).first()
        if not va:
            va = Artist(name="Various Artists", name_normalized="various artists")
            s.add(va)
            s.flush()

        target = Album(
            title=title_display, title_normalized=title_norm, artist_id=va.id,
            kind="playlist", owner_id=owner_id, year=year,
        )
        s.add(target)
        s.flush()

        if cover_src:
            srcp = settings.covers_dir / cover_src
            if srcp.is_file():
                dstp = settings.covers_dir / f"{target.id}{srcp.suffix}"
                try:
                    shutil.copyfile(srcp, dstp)
                    target.cover_path = dstp.name
                    s.add(target)
                except OSError as e:
                    print(f"  ! no pude copiar cover: {e}")

        if owner_id and not s.get(AlbumSave, (owner_id, target.id)):
            s.add(AlbumSave(user_id=owner_id, album_id=target.id))

        moved = 0
        for tid in tids:
            t = s.get(Track, tid)
            if not t:
                continue
            f = settings.music_dir / t.file_path
            if f.is_file():
                try:
                    au = mutagen.File(f, easy=True)
                    if au is not None:
                        au["album"] = title_display
                        au["albumartist"] = "Various Artists"
                        au.save()
                except Exception as e:  # noqa: BLE001
                    print(f"  ! tags {t.file_path}: {e}")
            t.album_id = target.id
            s.add(t)
            if not s.exec(
                select(AlbumTrack).where(
                    AlbumTrack.album_id == target.id, AlbumTrack.track_id == tid
                )
            ).first():
                s.add(AlbumTrack(album_id=target.id, track_id=tid))
            moved += 1

        for a in frags:
            for atrow in s.exec(select(AlbumTrack).where(AlbumTrack.album_id == a.id)).all():
                s.delete(atrow)
            for sv in s.exec(select(AlbumSave).where(AlbumSave.album_id == a.id)).all():
                s.delete(sv)
            lib._delete_album_record(s, a.id)

        print(f"Hecho: {moved} pistas → playlist id={target.id} '{title_display}', "
              f"{len(frags)} fragmentos borrados.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    title = args[0].strip().lower() if args else "makina"
    run(title, "--dry-run" in sys.argv)
