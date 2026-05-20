import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.config import settings
from app.db import get_session
from app.models import Album, Artist, Track
from app.services import library as library_svc
from app.services import lyrics as lyrics_svc
from app.services import organizer, scanner, spotify

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/tracks")
def list_tracks(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    artist_id: Optional[int] = None,
    album_id: Optional[int] = None,
    session: Session = Depends(get_session),
) -> dict:
    stmt = select(Track, Artist, Album).join(Artist, Track.artist_id == Artist.id).outerjoin(
        Album, Track.album_id == Album.id
    )
    if artist_id is not None:
        stmt = stmt.where(Track.artist_id == artist_id)
    if album_id is not None:
        stmt = stmt.where(Track.album_id == album_id)

    total = session.exec(
        select(func.count(Track.id)).select_from(Track)
    ).one()

    stmt = stmt.order_by(Album.title, Track.disc_number, Track.track_number, Track.title)
    stmt = stmt.limit(limit).offset(offset)

    items = []
    for track, artist, album in session.exec(stmt).all():
        items.append({
            "id": track.id,
            "title": track.title,
            "artist_id": artist.id,
            "artist_name": artist.name,
            "album_id": album.id if album else None,
            "album_title": album.title if album else None,
            "album_year": album.year if album else None,
            "cover_url": f"/api/library/cover/{album.id}" if album and album.cover_path else None,
            "track_number": track.track_number,
            "disc_number": track.disc_number,
            "duration_ms": track.duration_ms,
            "file_format": track.file_format,
            "stream_url": f"/api/library/stream/{track.id}",
        })

    return {"total": total, "limit": limit, "offset": offset, "items": items}


@router.get("/albums")
def list_albums(session: Session = Depends(get_session)) -> dict:
    stmt = (
        select(
            Album,
            Artist.name,
            func.count(Track.id).label("track_count"),
        )
        .join(Artist, Album.artist_id == Artist.id)
        .outerjoin(Track, Track.album_id == Album.id)
        .group_by(Album.id)
        .order_by(Artist.name, Album.year, Album.title)
    )
    items = [
        {
            "id": album.id,
            "title": album.title,
            "year": album.year,
            "artist_id": album.artist_id,
            "artist_name": artist_name,
            "track_count": track_count,
            "cover_url": f"/api/library/cover/{album.id}" if album.cover_path else None,
        }
        for album, artist_name, track_count in session.exec(stmt).all()
    ]
    return {"total": len(items), "items": items}


@router.get("/artists")
def list_artists(session: Session = Depends(get_session)) -> dict:
    stmt = (
        select(
            Artist,
            func.count(func.distinct(Album.id)).label("album_count"),
            func.count(func.distinct(Track.id)).label("track_count"),
        )
        .outerjoin(Album, Album.artist_id == Artist.id)
        .outerjoin(Track, Track.artist_id == Artist.id)
        .group_by(Artist.id)
        .order_by(Artist.name)
    )
    items = [
        {
            "id": artist.id,
            "name": artist.name,
            "album_count": album_count,
            "track_count": track_count,
        }
        for artist, album_count, track_count in session.exec(stmt).all()
    ]
    return {"total": len(items), "items": items}


@router.post("/scan")
def trigger_scan(background: BackgroundTasks) -> dict:
    if scanner.state.running:
        return {"started": False, "reason": "already running", "state": scanner.state.as_dict()}
    background.add_task(scanner.scan_library)
    return {"started": True, "state": scanner.state.as_dict()}


@router.get("/scan/status")
def scan_status() -> dict:
    return scanner.state.as_dict()


@router.post("/albums/{album_id}/cover")
async def upload_album_cover(
    album_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> dict:
    """Sube una nueva carátula para un álbum y la re-embebe en todos sus tracks."""
    album = session.get(Album, album_id)
    if album is None:
        raise HTTPException(404, "album not found")

    content = await file.read()
    if not content:
        raise HTTPException(400, "fichero vacío")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "demasiado grande (>10MB)")

    # Detectar tipo
    if content[:3] == b"\xff\xd8\xff":
        ext = ".jpg"
    elif content[:4] == b"\x89PNG":
        ext = ".png"
    else:
        raise HTTPException(400, "solo JPG o PNG")

    settings.covers_dir.mkdir(parents=True, exist_ok=True)
    cover_path = settings.covers_dir / f"{album_id}{ext}"
    cover_path.write_bytes(content)

    # Actualiza BD
    album.cover_path = cover_path.name
    session.add(album)
    session.flush()

    # Re-embebe en todos los tracks del álbum
    tracks = session.exec(select(Track).where(Track.album_id == album_id)).all()
    embedded = 0
    failed = 0
    for t in tracks:
        track_file = settings.music_dir / t.file_path
        if not track_file.is_file():
            failed += 1
            continue
        try:
            organizer.embed_cover(track_file, content)
            embedded += 1
        except Exception:
            failed += 1

    return {
        "ok": True,
        "cover_url": f"/api/library/cover/{album_id}",
        "tracks_updated": embedded,
        "tracks_failed": failed,
    }


@router.get("/search")
def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict:
    """Búsqueda case-insensitive sobre title/artist/album."""
    qlike = f"%{q.strip().lower()}%"
    stmt = (
        select(Track, Artist, Album)
        .join(Artist, Track.artist_id == Artist.id)
        .outerjoin(Album, Track.album_id == Album.id)
        .where(
            or_(
                func.lower(Track.title).like(qlike),
                func.lower(Artist.name).like(qlike),
                func.lower(Album.title).like(qlike),
            )
        )
        .limit(limit)
    )
    items = []
    for track, artist, album in session.exec(stmt).all():
        items.append({
            "id": track.id,
            "title": track.title,
            "artist_id": artist.id,
            "artist_name": artist.name,
            "album_id": album.id if album else None,
            "album_title": album.title if album else None,
            "album_year": album.year if album else None,
            "cover_url": f"/api/library/cover/{album.id}" if album and album.cover_path else None,
            "track_number": track.track_number,
            "disc_number": track.disc_number,
            "duration_ms": track.duration_ms,
            "file_format": track.file_format,
            "stream_url": f"/api/library/stream/{track.id}",
        })
    return {"query": q, "total": len(items), "items": items}


# ─── Borrado y edición ────────────────────────────────────────


@router.delete("/tracks/{track_id}")
def delete_track(track_id: int) -> dict:
    ok = library_svc.delete_track(track_id)
    if not ok:
        raise HTTPException(404, "track no encontrado")
    return {"ok": True}


class EditTrackIn(BaseModel):
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    track_number: Optional[int] = None
    disc_number: Optional[int] = None
    year: Optional[int] = None
    target_album_id: Optional[int] = None


@router.patch("/tracks/{track_id}")
def edit_track(track_id: int, body: EditTrackIn) -> dict:
    res = library_svc.edit_track(track_id, **body.model_dump(exclude_none=True))
    if not res.get("ok"):
        raise HTTPException(400, res.get("reason", "error"))
    return res


@router.delete("/albums/{album_id}")
def delete_album(album_id: int) -> dict:
    res = library_svc.delete_album(album_id)
    if not res.get("deleted"):
        raise HTTPException(404, res.get("reason", "no encontrado"))
    return res


class EditAlbumIn(BaseModel):
    title: Optional[str] = None
    year: Optional[int] = None


@router.patch("/albums/{album_id}")
def edit_album(album_id: int, body: EditAlbumIn) -> dict:
    res = library_svc.edit_album(album_id, **body.model_dump(exclude_none=True))
    if not res.get("ok"):
        raise HTTPException(400, res.get("reason", "error"))
    return res


# ─── Letras (LRCLIB) ──────────────────────────────────────────


@router.get("/tracks/{track_id}/lyrics")
def get_lyrics(track_id: int, session: Session = Depends(get_session)) -> dict:
    t = session.get(Track, track_id)
    if not t:
        raise HTTPException(404, "track no encontrado")
    artist = session.get(Artist, t.artist_id)
    album = session.get(Album, t.album_id) if t.album_id else None
    return lyrics_svc.fetch_lyrics(
        artist=artist.name if artist else "",
        title=t.title,
        album=album.title if album else None,
        duration_seconds=(t.duration_ms or 0) // 1000,
    )


# ─── Upload local ─────────────────────────────────────────────


@router.post("/upload")
async def upload_track(
    file: UploadFile = File(...),
    album: Optional[str] = Form(None),
    artist: Optional[str] = Form(None),
    year: Optional[int] = Form(None),
    target_album_id: Optional[int] = Form(None),
) -> dict:
    """Sube un fichero local y lo añade a la biblioteca con metadata opcional."""
    AUDIO_EXTS = {".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".wav"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in AUDIO_EXTS:
        raise HTTPException(
            400, f"extensión no soportada: {suffix} (soporto {', '.join(sorted(AUDIO_EXTS))})"
        )

    tmp_dir = settings.data_dir / "uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"upload-{uuid.uuid4().hex}{suffix}"

    size = 0
    with tmp_path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > 500 * 1024 * 1024:
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(400, "fichero demasiado grande (>500MB)")
            out.write(chunk)

    # Leer tags del fichero
    import mutagen
    try:
        au = mutagen.File(tmp_path, easy=True)
    except Exception:
        au = None
    file_tags = au.tags if au and au.tags else {}

    def _first(key: str, default: str = "") -> str:
        v = file_tags.get(key)
        if isinstance(v, list) and v:
            return str(v[0])
        return str(v) if v else default

    duration_ms = int((au.info.length * 1000) if au and au.info else 0)

    # Construir meta combinando tags del fichero + overrides
    detected_artist = _first("artist") or _first("albumartist") or "Unknown Artist"
    detected_album = _first("album")
    detected_title = _first("title") or Path(file.filename or "").stem

    meta = spotify.TrackMeta(
        spotify_id=f"upload:{uuid.uuid4().hex[:12]}",
        title=detected_title,
        artists=[artist or detected_artist],
        album=(album if album is not None else detected_album) or "",
        album_artist=artist or detected_artist,
        track_number=1,
        disc_number=1,
        total_tracks=1,
        duration_ms=duration_ms,
        isrc=None,
        year=year,
        cover_url=None,
        source_url="",
        source_kind="upload",
    )

    # Si nos dieron target_album_id, override desde BD
    if target_album_id:
        with library_svc.session_scope() as s:
            dest_album = s.get(Album, target_album_id)
            if dest_album:
                meta.album = dest_album.title
                dest_artist = s.get(Artist, dest_album.artist_id)
                if dest_artist:
                    meta.album_artist = dest_artist.name
                    meta.artists = [dest_artist.name]
                if dest_album.year:
                    meta.year = dest_album.year

    final_path = organizer.organize(tmp_path, meta)
    track_id = scanner.index_file(final_path)
    return {
        "ok": True,
        "track_id": track_id,
        "title": meta.title,
        "artist": meta.primary_artist,
        "album": meta.album,
    }


@router.get("/stats")
def library_stats(session: Session = Depends(get_session)) -> dict:
    n_tracks = session.exec(select(func.count(Track.id))).one()
    n_albums = session.exec(select(func.count(Album.id))).one()
    n_artists = session.exec(select(func.count(Artist.id))).one()
    total_bytes = session.exec(select(func.coalesce(func.sum(Track.file_size), 0))).one()
    return {
        "tracks": n_tracks,
        "albums": n_albums,
        "artists": n_artists,
        "total_bytes": total_bytes,
    }
