from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, select

from app.db import get_session
from app.models import Album, Artist, Track
from app.services import scanner

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
