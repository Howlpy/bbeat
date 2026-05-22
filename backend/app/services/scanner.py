"""Indexa data/music/ en la BD leyendo tags con Mutagen."""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from mutagen import File as MutagenFile
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from sqlmodel import Session, select

from app.config import settings
from app.db import session_scope
from app.models import Album, Artist, Track

log = logging.getLogger("bbeat.scanner")

AUDIO_EXTS = {".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".wav"}


@dataclass
class ScanState:
    running: bool = False
    started_at: float = 0
    finished_at: float = 0
    total_files: int = 0
    processed: int = 0
    added: int = 0
    updated: int = 0
    removed: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "running": self.running,
            "started_at": self.started_at or None,
            "finished_at": self.finished_at or None,
            "total_files": self.total_files,
            "processed": self.processed,
            "added": self.added,
            "updated": self.updated,
            "removed": self.removed,
            "errors": self.errors[-20:],
        }


state = ScanState()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _first(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value)


def _parse_int(v) -> Optional[int]:
    s = _first(v)
    if not s:
        return None
    s = s.split("/")[0].strip()
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def _parse_year(v) -> Optional[int]:
    s = _first(v)
    if not s:
        return None
    m = re.search(r"\d{4}", s)
    return int(m.group()) if m else None


def _extract_tags(audio) -> dict:
    """Devuelve dict normalizado independientemente del formato de tags."""
    t = audio.tags or {}

    def g(*keys):
        for k in keys:
            v = t.get(k) if hasattr(t, "get") else None
            if v:
                return v
        return None

    return {
        "title": _first(g("TIT2", "title", "\xa9nam")),
        "artist": _first(g("TPE1", "artist", "\xa9ART", "ARTIST")),
        "album": _first(g("TALB", "album", "\xa9alb", "ALBUM")),
        "album_artist": _first(g("TPE2", "albumartist", "aART")),
        "track_number": _parse_int(g("TRCK", "tracknumber", "trkn")),
        "disc_number": _parse_int(g("TPOS", "discnumber", "disk")),
        "year": _parse_year(g("TDRC", "TYER", "date", "\xa9day", "year")),
    }


def _extract_cover_bytes(audio) -> Optional[bytes]:
    """Devuelve los bytes de la carátula embebida o None."""
    if isinstance(audio, FLAC) and audio.pictures:
        return audio.pictures[0].data
    if isinstance(audio, MP3) and audio.tags:
        for k in audio.tags.keys():
            if k.startswith("APIC"):
                tag = audio.tags[k]
                if isinstance(tag, APIC):
                    return tag.data
    if isinstance(audio, MP4) and audio.tags:
        covers = audio.tags.get("covr")
        if covers:
            return bytes(covers[0])
    if isinstance(audio, OggVorbis) and audio.tags:
        b64 = audio.tags.get("metadata_block_picture")
        if b64:
            import base64
            try:
                pic = Picture(base64.b64decode(b64[0]))
                return pic.data
            except Exception:
                pass
    return None


def _save_cover(album_id: int, data: bytes) -> Optional[str]:
    settings.covers_dir.mkdir(parents=True, exist_ok=True)
    ext = ".jpg" if data[:3] == b"\xff\xd8\xff" else ".png" if data[:4] == b"\x89PNG" else ".jpg"
    path = settings.covers_dir / f"{album_id}{ext}"
    try:
        path.write_bytes(data)
        return f"{album_id}{ext}"
    except OSError as e:
        log.warning("No pude guardar cover %s: %s", path, e)
        return None


def save_track_cover(track_id: int, data: bytes) -> bool:
    """Guarda la carátula propia de una pista en covers/track-{id}.{jpg,png}."""
    settings.covers_dir.mkdir(parents=True, exist_ok=True)
    ext = ".jpg" if data[:3] == b"\xff\xd8\xff" else ".png" if data[:4] == b"\x89PNG" else ".jpg"
    try:
        (settings.covers_dir / f"track-{track_id}{ext}").write_bytes(data)
        return True
    except OSError as e:
        log.warning("No pude guardar cover de pista %s: %s", track_id, e)
        return False


def backfill_track_covers() -> dict:
    """Asigna carátula propia a cada pista: usa la embebida; si no hay y la pista
    viene de YouTube, baja la miniatura, la embebe y la guarda."""
    from app.services import organizer

    embedded = saved = 0
    with session_scope() as s:
        tracks = s.exec(select(Track)).all()
        for t in tracks:
            fpath = settings.music_dir / t.file_path
            if not fpath.is_file():
                continue
            au = MutagenFile(fpath)
            data = _extract_cover_bytes(au) if au else None
            if not data and t.source_url:
                m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", t.source_url)
                if m:
                    cd = organizer._fetch_cover_bytes(
                        f"https://i.ytimg.com/vi/{m.group(1)}/hqdefault.jpg"
                    )
                    if cd:
                        try:
                            organizer.embed_cover(fpath, cd)
                            data = cd
                            embedded += 1
                        except Exception:
                            pass
            if data and save_track_cover(t.id, data):
                if not t.has_cover:
                    t.has_cover = True
                    s.add(t)
                saved += 1
    return {"embedded": embedded, "saved": saved}


def _get_or_create_artist(session: Session, name: str) -> Artist:
    normalized = _norm(name)
    artist = session.exec(select(Artist).where(Artist.name_normalized == normalized)).first()
    if artist:
        return artist
    artist = Artist(name=name.strip(), name_normalized=normalized)
    session.add(artist)
    session.flush()
    return artist


def _get_or_create_album(
    session: Session,
    title: str,
    artist_id: int,
    year: Optional[int],
) -> Album:
    normalized = _norm(title)
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
        title=title.strip(),
        title_normalized=normalized,
        artist_id=artist_id,
        year=year,
    )
    session.add(album)
    session.flush()
    return album


def _index_one(session: Session, path: Path) -> str:
    """Indexa un fichero. Devuelve 'added'|'updated'|'skipped'."""
    audio = MutagenFile(path)
    if audio is None or not audio.info:
        raise ValueError("no se pudo leer como audio")

    tags = _extract_tags(audio)
    title = tags["title"] or path.stem
    artist_name = tags["album_artist"] or tags["artist"] or "Unknown Artist"
    album_title = tags["album"] or "Unknown Album"

    artist = _get_or_create_artist(session, artist_name)
    album = _get_or_create_album(session, album_title, artist.id, tags["year"])

    cover_bytes = _extract_cover_bytes(audio)
    if cover_bytes and not album.cover_path:
        album.cover_path = _save_cover(album.id, cover_bytes)
        session.add(album)

    rel_path = str(path.relative_to(settings.music_dir))
    info = audio.info

    track = session.exec(select(Track).where(Track.file_path == rel_path)).first()

    fields = {
        "title": title.strip(),
        "artist_id": artist.id,
        "album_id": album.id,
        "track_number": tags["track_number"],
        "disc_number": tags["disc_number"],
        "duration_ms": int(getattr(info, "length", 0) * 1000) or None,
        "file_size": path.stat().st_size,
        "file_format": path.suffix.lower().lstrip("."),
        "bitrate": getattr(info, "bitrate", None),
        "sample_rate": getattr(info, "sample_rate", None),
        "last_scanned": __import__("datetime").datetime.utcnow(),
    }

    if track is None:
        track = Track(file_path=rel_path, **fields)
        session.add(track)
        status = "added"
    else:
        status = "skipped"
        for k, v in fields.items():
            if getattr(track, k) != v:
                setattr(track, k, v)
                status = "updated"
        if status == "updated":
            session.add(track)

    # Carátula propia de la pista (independiente del álbum).
    if cover_bytes and not track.has_cover:
        session.flush()  # asegura track.id
        if save_track_cover(track.id, cover_bytes):
            track.has_cover = True
            session.add(track)

    return status


def index_file(path: Path) -> Optional[int]:
    """Indexa un único fichero (tras descarga). Devuelve track_id o None."""
    if not path.is_file() or path.suffix.lower() not in AUDIO_EXTS:
        return None
    with session_scope() as session:
        try:
            _index_one(session, path)
        except Exception as e:
            log.warning("index_file falló %s: %s", path, e)
            return None
        rel = str(path.relative_to(settings.music_dir))
        from app.models import Track  # local import para evitar ciclos
        from sqlmodel import select
        tr = session.exec(select(Track).where(Track.file_path == rel)).first()
        return tr.id if tr else None


def scan_library() -> dict:
    """Escaneo completo de settings.music_dir. Reentrante: no corre dos a la vez."""
    if state.running:
        log.info("Scan ya en curso, ignorando trigger")
        return state.as_dict()

    state.__init__()  # reset
    state.running = True
    state.started_at = time.time()
    log.info("Scan arrancando en %s", settings.music_dir)

    try:
        settings.music_dir.mkdir(parents=True, exist_ok=True)
        files = [
            p for p in settings.music_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in AUDIO_EXTS
        ]
        state.total_files = len(files)

        seen_paths: set[str] = set()
        with session_scope() as session:
            for path in files:
                try:
                    result = _index_one(session, path)
                    if result == "added":
                        state.added += 1
                    elif result == "updated":
                        state.updated += 1
                    seen_paths.add(str(path.relative_to(settings.music_dir)))
                except Exception as e:
                    msg = f"{path.name}: {e}"
                    log.warning(msg)
                    state.errors.append(msg)
                finally:
                    state.processed += 1

            # Limpiar tracks cuyo fichero ha desaparecido
            all_tracks = session.exec(select(Track)).all()
            for t in all_tracks:
                if t.file_path not in seen_paths:
                    session.delete(t)
                    state.removed += 1

    finally:
        state.running = False
        state.finished_at = time.time()
        log.info(
            "Scan terminado: +%d nuevos, %d actualizados, %d eliminados, %d errores",
            state.added, state.updated, state.removed, len(state.errors),
        )
    return state.as_dict()
