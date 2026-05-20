"""Streaming de audio con soporte HTTP Range (esencial en móvil para seek)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlmodel import Session, select

from app.config import settings
from app.db import get_session
from app.models import Album, Track

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
):
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
def get_cover(album_id: int, session: Session = Depends(get_session)):
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
