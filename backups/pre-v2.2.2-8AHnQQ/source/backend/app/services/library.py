"""Operaciones de gestión: borrar, editar, mover tracks/álbumes."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app.config import settings
from app.db import session_scope
from app.models import (
    Album,
    AlbumSave,
    AlbumTrack,
    Artist,
    Job,
    Play,
    Track,
    TrackLike,
)
from app.services import organizer

log = logging.getLogger("bbeat.library")


# ─── Helpers ──────────────────────────────────────────────────


def _safe_path_in(base: Path, candidate: Path) -> Path:
    """Asegura que candidate está dentro de base, o lanza ValueError."""
    base_r = base.resolve()
    cand_r = candidate.resolve()
    try:
        cand_r.relative_to(base_r)
    except ValueError:
        raise ValueError(f"path fuera de {base_r}: {cand_r}")
    return cand_r


def _delete_file_safe(path: Path) -> None:
    try:
        full = _safe_path_in(settings.music_dir, path)
        if full.is_file():
            full.unlink()
            log.info("borrado %s", full)
        # Borrar carpeta si queda vacía (album y artista)
        parent = full.parent
        for _ in range(2):  # max sube 2 niveles (album, artist)
            try:
                if parent.is_dir() and not any(parent.iterdir()):
                    parent.rmdir()
                    log.info("carpeta vacía borrada %s", parent)
                else:
                    break
            except OSError:
                break
            parent = parent.parent
    except Exception as e:
        log.warning("no pude borrar %s: %s", path, e)


def _get_or_create_artist(session: Session, name: str) -> Artist:
    import re as _re
    normalized = _re.sub(r"\s+", " ", (name or "").strip().lower()) or "unknown artist"
    artist = session.exec(
        select(Artist).where(Artist.name_normalized == normalized)
    ).first()
    if artist:
        return artist
    artist = Artist(name=name.strip() or "Unknown Artist", name_normalized=normalized)
    session.add(artist)
    session.flush()
    return artist


def _get_or_create_album(
    session: Session, title: str, artist_id: int, year: Optional[int]
) -> Album:
    import re as _re
    normalized = _re.sub(r"\s+", " ", (title or "").strip().lower()) or "unknown album"
    album = session.exec(
        select(Album).where(
            Album.title_normalized == normalized, Album.artist_id == artist_id
        )
    ).first()
    if album:
        if year and not album.year:
            album.year = year
            session.add(album)
        return album
    album = Album(
        title=(title or "Unknown Album").strip(),
        title_normalized=normalized,
        artist_id=artist_id,
        year=year,
    )
    session.add(album)
    session.flush()
    return album


def _meta_from_track(session: Session, track: Track) -> "spotify.TrackMeta":
    from app.services.spotify import TrackMeta

    artist = session.get(Artist, track.artist_id)
    album = session.get(Album, track.album_id) if track.album_id else None
    artist_name = artist.name if artist else "Unknown Artist"
    return TrackMeta(
        spotify_id=str(track.id),
        title=track.title,
        artists=[artist_name],
        album=album.title if album else "",
        album_artist=artist_name,
        track_number=track.track_number or 1,
        disc_number=track.disc_number or 1,
        total_tracks=1,
        duration_ms=track.duration_ms or 0,
        isrc=None,
        year=album.year if album else None,
        cover_url=None,
        source_url="",
        source_kind="track",
    )


# ─── Borrado ──────────────────────────────────────────────────


def _detach_track_references(s: Session, track_id: int) -> None:
    """Limpia todas las FK hacia una pista antes de borrarla."""
    for model in (AlbumTrack, TrackLike, Play):
        for row in s.exec(select(model).where(model.track_id == track_id)).all():
            s.delete(row)
    for job in s.exec(select(Job).where(Job.result_track_id == track_id)).all():
        job.result_track_id = None
        s.add(job)


def _detach_album_references(s: Session, album_id: int) -> None:
    """Limpia membresías, guardados y destinos de jobs de un álbum."""
    for at in s.exec(select(AlbumTrack).where(AlbumTrack.album_id == album_id)).all():
        s.delete(at)
    for saved in s.exec(select(AlbumSave).where(AlbumSave.album_id == album_id)).all():
        s.delete(saved)
    for job in s.exec(select(Job).where(Job.target_album_id == album_id)).all():
        job.target_album_id = None
        s.add(job)


def delete_track(track_id: int) -> bool:
    with session_scope() as s:
        t = s.get(Track, track_id)
        if not t:
            return False
        file_path = settings.music_dir / t.file_path
        album_id = t.album_id
        artist_id = t.artist_id
        _detach_track_references(s, track_id)
        s.delete(t)
        s.flush()
        _delete_file_safe(file_path)
        # Borrar la carátula propia de la pista si existe
        for ext in (".jpg", ".png"):
            cp = settings.covers_dir / f"track-{track_id}{ext}"
            if cp.is_file():
                try:
                    cp.unlink()
                except OSError:
                    pass
        # Si el álbum se quedó sin pistas, borrarlo (y carátula)
        if album_id:
            remaining = s.exec(
                select(Track).where(Track.album_id == album_id).limit(1)
            ).first()
            if not remaining:
                _delete_album_record(s, album_id)
        # Si el artista se quedó sin pistas, borrarlo
        if artist_id:
            remaining = s.exec(
                select(Track).where(Track.artist_id == artist_id).limit(1)
            ).first()
            if not remaining:
                art = s.get(Artist, artist_id)
                if art:
                    s.delete(art)
        return True


def _delete_album_record(s: Session, album_id: int) -> None:
    album = s.get(Album, album_id)
    if not album:
        return
    _detach_album_references(s, album_id)
    if album.cover_path:
        try:
            cp = settings.covers_dir / album.cover_path
            if cp.is_file():
                cp.unlink()
        except OSError:
            pass
    s.delete(album)


def delete_album(album_id: int) -> dict:
    """Borra un álbum completo: todos sus tracks, ficheros y la carátula."""
    deleted_tracks = 0
    with session_scope() as s:
        album = s.get(Album, album_id)
        if not album:
            return {"deleted": False, "reason": "no encontrado"}
        artist_id = album.artist_id
        tracks = s.exec(select(Track).where(Track.album_id == album_id)).all()
        for t in tracks:
            file_path = settings.music_dir / t.file_path
            _detach_track_references(s, t.id)
            s.delete(t)
            _delete_file_safe(file_path)
            deleted_tracks += 1
        _delete_album_record(s, album_id)
        s.flush()
        # ¿Artista huérfano?
        if artist_id:
            remaining = s.exec(
                select(Track).where(Track.artist_id == artist_id).limit(1)
            ).first()
            if not remaining:
                art = s.get(Artist, artist_id)
                if art:
                    s.delete(art)
    return {"deleted": True, "tracks_deleted": deleted_tracks}


# ─── Edición de track ─────────────────────────────────────────


def edit_track(
    track_id: int,
    *,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    album: Optional[str] = None,
    track_number: Optional[int] = None,
    disc_number: Optional[int] = None,
    year: Optional[int] = None,
    target_album_id: Optional[int] = None,
) -> dict:
    """Cambia metadata del track. Si artist/album cambian, reubica el fichero
    en disco y re-escribe los tags. target_album_id (si se da) tiene prioridad
    sobre album/year y reusa Artist del álbum destino.
    """
    with session_scope() as s:
        t = s.get(Track, track_id)
        if not t:
            return {"ok": False, "reason": "no encontrado"}

        # Resolver destino
        if target_album_id is not None:
            dest_album = s.get(Album, target_album_id)
            if not dest_album:
                return {"ok": False, "reason": "álbum destino no existe"}
            dest_artist = s.get(Artist, dest_album.artist_id)
            artist_name = dest_artist.name if dest_artist else "Unknown Artist"
            album_name = dest_album.title
            year_v = dest_album.year
        else:
            cur_artist = s.get(Artist, t.artist_id)
            artist_name = (artist or (cur_artist.name if cur_artist else "Unknown Artist")).strip()
            cur_album = s.get(Album, t.album_id) if t.album_id else None
            album_name = (album if album is not None else (cur_album.title if cur_album else "")).strip()
            year_v = year if year is not None else (cur_album.year if cur_album else None)

        # Asegurar artist + album en BD
        new_artist = _get_or_create_artist(s, artist_name)
        new_album = _get_or_create_album(s, album_name, new_artist.id, year_v) if album_name else None

        old_path = settings.music_dir / t.file_path
        ext = old_path.suffix.lower()

        new_title = (title if title is not None else t.title).strip() or t.title
        new_track_no = track_number if track_number is not None else t.track_number
        new_disc_no = disc_number if disc_number is not None else t.disc_number

        # Construir destino (uso del organizer.target_path con meta inventada)
        from app.services.spotify import TrackMeta

        meta = TrackMeta(
            spotify_id=str(t.id),
            title=new_title,
            artists=[artist_name],
            album=album_name,
            album_artist=artist_name,
            track_number=new_track_no or 1,
            disc_number=new_disc_no or 1,
            total_tracks=1,
            duration_ms=t.duration_ms or 0,
            isrc=None,
            year=year_v,
            cover_url=None,
            source_url="",
            source_kind="track",
        )
        new_path = organizer.target_path(meta, ext)
        new_path.parent.mkdir(parents=True, exist_ok=True)

        # Mover si cambió
        if new_path != old_path:
            if new_path.exists():
                # añadir sufijo .1, .2... para evitar pisar
                stem = new_path.stem
                i = 1
                while new_path.exists():
                    new_path = new_path.with_name(f"{stem} ({i}){ext}")
                    i += 1
            shutil.move(str(old_path), new_path)
            # Limpieza de carpetas vacías
            try:
                old_path.parent.rmdir()
                old_path.parent.parent.rmdir()
            except OSError:
                pass

        # Re-escribir tags en el fichero
        try:
            organizer.write_tags(new_path, meta)
        except Exception as e:
            log.warning("write_tags falló para %s: %s", new_path, e)

        # Actualizar BD
        old_album_id = t.album_id
        old_artist_id = t.artist_id
        t.title = new_title
        t.artist_id = new_artist.id
        t.album_id = new_album.id if new_album else None
        t.track_number = new_track_no
        t.disc_number = new_disc_no
        t.file_path = str(new_path.relative_to(settings.music_dir))
        s.add(t)
        s.flush()

        # Limpiar álbum/artista huérfanos
        for aid in (old_album_id,):
            if aid and aid != t.album_id:
                rem = s.exec(select(Track).where(Track.album_id == aid).limit(1)).first()
                if not rem:
                    _delete_album_record(s, aid)
        for aid in (old_artist_id,):
            if aid and aid != t.artist_id:
                rem = s.exec(select(Track).where(Track.artist_id == aid).limit(1)).first()
                if not rem:
                    a = s.get(Artist, aid)
                    if a:
                        s.delete(a)

        return {"ok": True, "track_id": t.id, "file_path": t.file_path}


# ─── Renombrar/editar álbum ───────────────────────────────────


def edit_album(album_id: int, *, title: Optional[str] = None, year: Optional[int] = None) -> dict:
    """Renombra el álbum y mueve la carpeta con todos sus tracks."""
    with session_scope() as s:
        album = s.get(Album, album_id)
        if not album:
            return {"ok": False, "reason": "no encontrado"}

        new_title = (title if title is not None else album.title).strip() or album.title
        new_year = year if year is not None else album.year

        if new_title == album.title and new_year == album.year:
            return {"ok": True, "unchanged": True}

        # Aplicar a la BD del álbum
        import re as _re
        album.title = new_title
        album.title_normalized = _re.sub(r"\s+", " ", new_title.lower())
        album.year = new_year
        s.add(album)
        s.flush()

        # Mover cada track a la nueva ubicación
        tracks = s.exec(select(Track).where(Track.album_id == album_id)).all()
        artist = s.get(Artist, album.artist_id)
        artist_name = artist.name if artist else "Unknown Artist"
        moved = 0
        for t in tracks:
            old_path = settings.music_dir / t.file_path
            if not old_path.is_file():
                continue
            from app.services.spotify import TrackMeta

            meta = TrackMeta(
                spotify_id=str(t.id),
                title=t.title,
                artists=[artist_name],
                album=new_title,
                album_artist=artist_name,
                track_number=t.track_number or 1,
                disc_number=t.disc_number or 1,
                total_tracks=1,
                duration_ms=t.duration_ms or 0,
                isrc=None,
                year=new_year,
                cover_url=None,
                source_url="",
                source_kind="track",
            )
            new_path = organizer.target_path(meta, old_path.suffix.lower())
            new_path.parent.mkdir(parents=True, exist_ok=True)
            if new_path != old_path:
                if new_path.exists():
                    continue
                shutil.move(str(old_path), new_path)
                try:
                    old_path.parent.rmdir()
                except OSError:
                    pass
            try:
                organizer.write_tags(new_path, meta)
            except Exception:
                pass
            t.file_path = str(new_path.relative_to(settings.music_dir))
            s.add(t)
            moved += 1
        return {"ok": True, "moved": moved}
