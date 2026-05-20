"""Mueve un fichero descargado a la biblioteca con nombre limpio y tags + cover."""
from __future__ import annotations

import base64
import logging
import re
import shutil
from pathlib import Path
from typing import Optional

import httpx
import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, APIC, ID3NoHeaderError
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis

from app.config import settings
from app.services.spotify import TrackMeta

log = logging.getLogger("bbeat.organizer")

INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize(name: str, max_len: int = 180) -> str:
    name = INVALID_CHARS.sub("_", name).strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    if not name:
        name = "unknown"
    return name[:max_len]


def target_path(meta: TrackMeta, ext: str) -> Path:
    artist = sanitize(meta.album_artist or meta.primary_artist)
    if meta.album:
        album_label = f"{meta.album} ({meta.year})" if meta.year else meta.album
    else:
        # Sin álbum (track URL o playlist) → carpeta Singles del artista
        album_label = "Singles"
    album = sanitize(album_label)
    if meta.album and meta.track_number:
        filename = sanitize(f"{meta.track_number:02d} - {meta.title}{ext}")
    else:
        filename = sanitize(f"{meta.title}{ext}")
    return settings.music_dir / artist / album / filename


def _fetch_cover_bytes(url: str) -> Optional[bytes]:
    try:
        with httpx.Client(timeout=15) as c:
            r = c.get(url)
            r.raise_for_status()
            return r.content
    except Exception as e:
        log.warning("no pude bajar cover %s: %s", url, e)
        return None


def _cover_mime(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"\x89PNG":
        return "image/png"
    return "image/jpeg"


def _embed_cover_mp3(path: Path, data: bytes, mime: str) -> None:
    try:
        audio = MP3(path, ID3=ID3)
    except ID3NoHeaderError:
        audio = MP3(path)
        audio.add_tags()
    if audio.tags is None:
        audio.add_tags()
    # Quitar covers antiguos para no duplicar
    audio.tags.delall("APIC")
    audio.tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=data))
    audio.save()


def _embed_cover_ogg(path: Path, data: bytes, mime: str, kind: str) -> None:
    audio = OggOpus(path) if kind == "opus" else OggVorbis(path)
    pic = Picture()
    pic.data = data
    pic.mime = mime
    pic.type = 3
    pic.width = 640
    pic.height = 640
    pic.depth = 24
    b64 = base64.b64encode(pic.write()).decode("ascii")
    audio["metadata_block_picture"] = [b64]
    audio.save()


def _embed_cover_flac(path: Path, data: bytes, mime: str) -> None:
    audio = FLAC(path)
    audio.clear_pictures()
    pic = Picture()
    pic.data = data
    pic.mime = mime
    pic.type = 3
    audio.add_picture(pic)
    audio.save()


def _embed_cover_mp4(path: Path, data: bytes, mime: str) -> None:
    audio = MP4(path)
    fmt = MP4Cover.FORMAT_JPEG if mime == "image/jpeg" else MP4Cover.FORMAT_PNG
    audio["covr"] = [MP4Cover(data, imageformat=fmt)]
    audio.save()


def embed_cover(path: Path, data: bytes) -> None:
    ext = path.suffix.lower()
    mime = _cover_mime(data)
    if ext == ".mp3":
        _embed_cover_mp3(path, data, mime)
    elif ext == ".flac":
        _embed_cover_flac(path, data, mime)
    elif ext == ".ogg":
        _embed_cover_ogg(path, data, mime, "vorbis")
    elif ext == ".opus":
        _embed_cover_ogg(path, data, mime, "opus")
    elif ext in (".m4a", ".mp4"):
        _embed_cover_mp4(path, data, mime)
    else:
        log.warning("embed_cover: extensión no soportada %s", ext)


def write_tags(path: Path, meta: TrackMeta) -> None:
    audio = mutagen.File(path, easy=True)
    if audio is None:
        raise ValueError(f"no es un fichero de audio: {path}")
    if audio.tags is None:
        audio.add_tags()

    audio["title"] = meta.title
    audio["artist"] = "; ".join(meta.artists) if meta.artists else "Unknown Artist"
    audio["album"] = meta.album or "Unknown Album"
    audio["albumartist"] = meta.album_artist or meta.primary_artist
    audio["tracknumber"] = f"{meta.track_number}/{meta.total_tracks}"
    audio["discnumber"] = str(meta.disc_number)
    if meta.year:
        audio["date"] = str(meta.year)
    if meta.isrc:
        try:
            audio["isrc"] = meta.isrc
        except (KeyError, mutagen.MutagenError):
            pass
    audio.save()


def organize(source: Path, meta: TrackMeta) -> Path:
    """Mueve el fichero a la ubicación final, etiqueta y embebe carátula."""
    ext = source.suffix.lower()
    dst = target_path(meta, ext)
    dst.parent.mkdir(parents=True, exist_ok=True)

    if dst.exists():
        log.info("destino ya existe, sobrescribiendo: %s", dst)
        dst.unlink()
    shutil.move(str(source), dst)

    # Tags
    try:
        write_tags(dst, meta)
    except Exception as e:
        log.warning("write_tags falló para %s: %s", dst, e)

    # Cover
    if meta.cover_url:
        cover_data = _fetch_cover_bytes(meta.cover_url)
        if cover_data:
            try:
                embed_cover(dst, cover_data)
            except Exception as e:
                log.warning("embed_cover falló para %s: %s", dst, e)

    log.info("organizada → %s", dst)
    return dst
