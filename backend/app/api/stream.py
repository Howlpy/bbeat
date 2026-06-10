"""Streaming de audio con soporte HTTP Range (esencial en móvil para seek)."""
from __future__ import annotations

import re
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Iterator

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlmodel import Session, select

from app.config import settings
from app.db import get_session
from app.models import Album, Track, User
from app.services import auth as auth_svc

log = __import__("logging").getLogger("bbeat.stream")

router = APIRouter(prefix="/library", tags=["stream"])

CHUNK_SIZE = 64 * 1024

CONTENT_TYPES = {
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
    "opus": "audio/ogg",
    "flac": "audio/flac",
    "m4a": "audio/mp4",
    "aac": "audio/aac",
    "wav": "audio/wav",
}

# Formatos que Subsonic puede pedir vía parámetro `format`
TRANSCODE_FORMATS = {
    "mp3": ("audio/mpeg", ["-f", "mp3", "-codec:a", "libmp3lame", "-q:a", "2"]),
    "aac": ("audio/aac", ["-f", "adts", "-codec:a", "aac", "-b:a", "192k"]),
    "ogg": ("audio/ogg", ["-f", "ogg", "-codec:a", "libvorbis", "-q:a", "6"]),
}

# Limita los procesos ffmpeg simultáneos para no saturar la CPU del host.
_transcode_sem = threading.Semaphore(max(1, settings.transcode_concurrency))


def _transcode_to_cache(src: Path, dest: Path, fmt: str) -> None:
    """Transcodifica src → dest usando ffmpeg. Escribe en un temporal único y hace
    rename atómico para que un fallo a mitad (o dos transcodes a la vez) no deje un
    fichero corrupto en cache. El semáforo acota el pico de CPU."""
    _, ffmpeg_args = TRANSCODE_FORMATS[fmt]
    tmp = dest.with_name(f"{dest.name}.{uuid.uuid4().hex}.tmp")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-threads", "1",          # un core por tarea, evita picos de CPU
        "-i", str(src),
        *ffmpeg_args,
        str(tmp),
    ]
    with _transcode_sem:
        try:
            subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
            tmp.rename(dest)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise


def _purge_transcache(cache_dir: Path) -> None:
    """Si la caché supera el tope, borra los ficheros menos usados recientemente
    (por mtime) hasta volver bajo el límite. Evita que data/transcache/ crezca sin
    fin en el disco del host. Best-effort: cualquier error de FS se ignora."""
    max_mb = settings.transcache_max_mb
    if max_mb <= 0:
        return
    try:
        files = [
            (f, f.stat()) for f in cache_dir.iterdir()
            if f.is_file() and not f.name.endswith(".tmp")
        ]
    except OSError:
        return
    total = sum(st.st_size for _, st in files)
    limit = max_mb * 1024 * 1024
    if total <= limit:
        return
    # Más antiguos primero (LRU aproximado por mtime).
    for f, st in sorted(files, key=lambda fs: fs[1].st_mtime):
        if total <= limit:
            break
        try:
            f.unlink()
            total -= st.st_size
        except OSError:
            pass


def get_transcoded(track_id: int, src: Path, fmt: str) -> Path:
    """Devuelve la ruta del fichero transcodificado, generándolo si no existe."""
    cache_dir = settings.transcache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{track_id}.{fmt}"
    if cached.is_file():
        # Marca el uso para que la purga LRU respete lo que se reproduce a menudo.
        try:
            cached.touch()
        except OSError:
            pass
        return cached
    log.info("transcoding track %d → %s", track_id, fmt)
    _transcode_to_cache(src, cached, fmt)
    _purge_transcache(cache_dir)
    return cached


def _parse_range(header: str, file_size: int) -> tuple[int, int] | None:
    """Parsea 'bytes=START-END' devolviendo (start, end inclusivo)."""
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
    if not m:
        return None
    start_s, end_s = m.group(1), m.group(2)
    if start_s == "" and end_s == "":
        return None
    if start_s == "":
        # bytes=-N → últimos N bytes
        suffix = int(end_s)
        if suffix <= 0:
            return None
        start = max(file_size - suffix, 0)
        end = file_size - 1
    else:
        start = int(start_s)
        end = int(end_s) if end_s else file_size - 1
    if start > end or start >= file_size:
        return None
    end = min(end, file_size - 1)
    return start, end


def _iter_file_range(path: Path, start: int, end: int) -> Iterator[bytes]:
    remaining = end - start + 1
    with path.open("rb") as f:
        f.seek(start)
        while remaining > 0:
            chunk = f.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.get("/stream/{track_id}")
def stream_track(
    track_id: int,
    request: Request,
    range_header: str | None = Header(default=None, alias="Range"),
    session: Session = Depends(get_session),
    user: User = Depends(auth_svc.get_current_user),
):
    # Pool global: cualquier usuario autenticado puede reproducir cualquier pista.
    track = session.get(Track, track_id)
    if track is None:
        raise HTTPException(404, "track not found")

    path = (settings.music_dir / track.file_path).resolve()
    if not path.is_file():
        raise HTTPException(410, "file gone")

    # Sanity: el path debe quedar dentro de music_dir
    try:
        path.relative_to(settings.music_dir.resolve())
    except ValueError:
        raise HTTPException(400, "invalid path")

    file_size = path.stat().st_size
    media_type = CONTENT_TYPES.get(track.file_format or "", "application/octet-stream")

    base_headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=3600",
    }

    if range_header:
        parsed = _parse_range(range_header, file_size)
        if parsed is None:
            return Response(
                status_code=416,
                headers={"Content-Range": f"bytes */{file_size}"},
            )
        start, end = parsed
        length = end - start + 1
        headers = {
            **base_headers,
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(length),
        }
        return StreamingResponse(
            _iter_file_range(path, start, end),
            status_code=206,
            media_type=media_type,
            headers=headers,
        )

    return FileResponse(
        path,
        media_type=media_type,
        headers={**base_headers, "Content-Length": str(file_size)},
    )


@router.get("/cover/{album_id}")
def get_cover(
    album_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(auth_svc.get_current_user),
):
    # Pool global: las carátulas son visibles para cualquier usuario autenticado.
    album = session.get(Album, album_id)
    if album is None or not album.cover_path:
        raise HTTPException(404, "cover not found")
    path = (settings.covers_dir / album.cover_path).resolve()
    if not path.is_file():
        raise HTTPException(404, "cover file missing")
    try:
        path.relative_to(settings.covers_dir.resolve())
    except ValueError:
        raise HTTPException(400, "invalid path")
    media_type = "image/jpeg" if path.suffix == ".jpg" else "image/png"
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/cover/track/{track_id}")
def get_track_cover(
    track_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(auth_svc.get_current_user),
):
    """Carátula propia de la pista (covers/track-{id}.{jpg,png})."""
    track = session.get(Track, track_id)
    if track is None or not getattr(track, "has_cover", False):
        raise HTTPException(404, "cover not found")
    for ext in (".jpg", ".png"):
        path = (settings.covers_dir / f"track-{track_id}{ext}").resolve()
        if path.is_file():
            try:
                path.relative_to(settings.covers_dir.resolve())
            except ValueError:
                raise HTTPException(400, "invalid path")
            return FileResponse(
                path,
                media_type="image/jpeg" if ext == ".jpg" else "image/png",
                headers={"Cache-Control": "public, max-age=86400"},
            )
    raise HTTPException(404, "cover file missing")
