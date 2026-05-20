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
from app.models import Album, AlbumTrack, Artist, Track, User
from app.services import access as access_svc
from app.services import auth as auth_svc
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
    user: User = Depends(auth_svc.get_current_user),
) -> dict:
    visible_ids = access_svc.visible_track_ids_subquery(user)
    stmt = (
        select(Track, Artist, Album)
        .join(Artist, Track.artist_id == Artist.id)
        .outerjoin(Album, Track.album_id == Album.id)
        .where(Track.id.in_(visible_ids))
    )
    if artist_id is not None:
        stmt = stmt.where(Track.artist_id == artist_id)
    if album_id is not None:
        # Vía AlbumTrack (M:N): incluye tracks que pertenecen al álbum aunque
        # su album_id "primario" sea otro.
        in_album_subq = select(AlbumTrack.track_id).where(AlbumTrack.album_id == album_id)
        stmt = stmt.where(Track.id.in_(in_album_subq))

    count_stmt = (
        select(func.count(Track.id))
        .select_from(Track)
        .where(Track.id.in_(visible_ids))
    )
    if album_id is not None:
        in_album_subq = select(AlbumTrack.track_id).where(AlbumTrack.album_id == album_id)
        count_stmt = count_stmt.where(Track.id.in_(in_album_subq))
    if artist_id is not None:
        count_stmt = count_stmt.where(Track.artist_id == artist_id)
    total = session.exec(count_stmt).one()

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
            "source_url": track.source_url,
        })

    return {"total": total, "limit": limit, "offset": offset, "items": items}


@router.get("/albums")
def list_albums(
    scope: str = Query("all", regex="^(all|mine|public)$"),
    session: Session = Depends(get_session),
    user: User = Depends(auth_svc.get_current_user),
) -> dict:
    stmt = (
        select(
            Album,
            Artist.name,
            func.count(AlbumTrack.track_id).label("track_count"),
        )
        .join(Artist, Album.artist_id == Artist.id)
        .outerjoin(AlbumTrack, AlbumTrack.album_id == Album.id)
        .group_by(Album.id)
        .order_by(Artist.name, Album.year, Album.title)
    )
    if user.is_admin and scope == "all":
        pass
    elif scope == "mine":
        stmt = stmt.where(Album.owner_id == user.id)
    elif scope == "public":
        stmt = stmt.where(Album.is_public == True)  # noqa: E712
    else:
        # 'all' para no-admin = mis álbumes + públicos
        stmt = stmt.where(or_(Album.owner_id == user.id, Album.is_public == True))  # noqa: E712
    items = [
        {
            "id": album.id,
            "title": album.title,
            "year": album.year,
            "artist_id": album.artist_id,
            "artist_name": artist_name,
            "track_count": track_count,
            "cover_url": f"/api/library/cover/{album.id}" if album.cover_path else None,
            "owner_id": album.owner_id,
            "is_public": album.is_public,
            "is_mine": album.owner_id == user.id,
        }
        for album, artist_name, track_count in session.exec(stmt).all()
    ]
    return {"total": len(items), "items": items}


@router.get("/artists")
def list_artists(
    session: Session = Depends(get_session),
    user: User = Depends(auth_svc.get_current_user),
) -> dict:
    visible = access_svc.visible_album_ids(session, user)
    stmt = (
        select(
            Artist,
            func.count(func.distinct(Album.id)).label("album_count"),
            func.count(func.distinct(Track.id)).label("track_count"),
        )
        .outerjoin(Album, (Album.artist_id == Artist.id) & (Album.id.in_(visible)))
        .outerjoin(
            Track,
            (Track.artist_id == Artist.id)
            & ((Track.album_id == None) | (Track.album_id.in_(visible))),  # noqa: E711
        )
        .group_by(Artist.id)
        .having(func.count(Track.id) > 0)
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
def trigger_scan(
    background: BackgroundTasks,
    _: User = Depends(auth_svc.require_admin),
) -> dict:
    if scanner.state.running:
        return {"started": False, "reason": "already running", "state": scanner.state.as_dict()}
    background.add_task(scanner.scan_library)
    return {"started": True, "state": scanner.state.as_dict()}


@router.get("/scan/status")
def scan_status(_: User = Depends(auth_svc.get_current_user)) -> dict:
    return scanner.state.as_dict()


class AddTracksIn(BaseModel):
    track_ids: list[int]


@router.post("/albums/{album_id}/tracks")
def add_tracks_to_album(
    album_id: int,
    body: AddTracksIn,
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Añade N pistas existentes a un álbum vía AlbumTrack (M:N). No descarga
    nada. Útil para componer colecciones a partir de la biblioteca compartida.
    """
    from app.models import AlbumTrack

    album = session.get(Album, album_id)
    if album is None:
        raise HTTPException(404, "álbum no encontrado")
    if not access_svc.can_mutate_album(album, user):
        raise HTTPException(403, "no es tuyo")

    if not body.track_ids:
        return {"added": 0, "already": 0, "denied": 0}

    visible_ids = set(
        session.exec(access_svc.visible_track_ids_subquery(user)).all()
    )
    added = 0
    already = 0
    denied = 0
    for tid in body.track_ids:
        if tid not in visible_ids:
            denied += 1
            continue
        existing = session.exec(
            select(AlbumTrack).where(
                AlbumTrack.album_id == album_id, AlbumTrack.track_id == tid
            )
        ).first()
        if existing:
            already += 1
            continue
        session.add(AlbumTrack(album_id=album_id, track_id=tid))
        added += 1

    return {"added": added, "already": already, "denied": denied}


@router.post("/albums/{album_id}/cover")
async def upload_album_cover(
    album_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(auth_svc.get_current_user),
) -> dict:
    """Sube una nueva carátula para un álbum y la re-embebe en todos sus tracks."""
    album = session.get(Album, album_id)
    if album is None:
        raise HTTPException(404, "album not found")
    if not access_svc.can_mutate_album(album, user):
        raise HTTPException(403, "no es tuyo")

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


@router.get("/recent")
def recent(
    limit: int = Query(12, ge=1, le=50),
    kind: str = Query("both", regex="^(tracks|albums|both)$"),
    session: Session = Depends(get_session),
    user: User = Depends(auth_svc.get_current_user),
) -> dict:
    """Últimas pistas/álbumes añadidos a la biblioteca del user."""
    visible_ids = access_svc.visible_track_ids_subquery(user)
    out: dict = {}
    if kind in ("tracks", "both"):
        stmt = (
            select(Track, Artist, Album)
            .join(Artist, Track.artist_id == Artist.id)
            .outerjoin(Album, Track.album_id == Album.id)
            .where(Track.id.in_(visible_ids))
            .order_by(Track.created_at.desc())
            .limit(limit)
        )
        out["tracks"] = [
            {
                "id": t.id,
                "title": t.title,
                "artist_id": ar.id,
                "artist_name": ar.name,
                "album_id": al.id if al else None,
                "album_title": al.title if al else None,
                "album_year": al.year if al else None,
                "cover_url": f"/api/library/cover/{al.id}" if al and al.cover_path else None,
                "track_number": t.track_number,
                "disc_number": t.disc_number,
                "duration_ms": t.duration_ms,
                "file_format": t.file_format,
                "stream_url": f"/api/library/stream/{t.id}",
                "source_url": t.source_url,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t, ar, al in session.exec(stmt).all()
        ]
    if kind in ("albums", "both"):
        visible_albums = access_svc.visible_album_ids(session, user)
        stmt = (
            select(Album, Artist.name, func.count(AlbumTrack.track_id).label("tc"))
            .join(Artist, Album.artist_id == Artist.id)
            .outerjoin(AlbumTrack, AlbumTrack.album_id == Album.id)
            .where(Album.id.in_(visible_albums))
            .group_by(Album.id)
            .order_by(Album.created_at.desc())
            .limit(limit)
        )
        out["albums"] = [
            {
                "id": a.id,
                "title": a.title,
                "year": a.year,
                "artist_id": a.artist_id,
                "artist_name": an,
                "track_count": tc,
                "cover_url": f"/api/library/cover/{a.id}" if a.cover_path else None,
                "owner_id": a.owner_id,
                "is_public": a.is_public,
                "is_mine": a.owner_id == user.id,
            }
            for a, an, tc in session.exec(stmt).all()
        ]
    return out


@router.get("/search")
def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
    user: User = Depends(auth_svc.get_current_user),
) -> dict:
    """Búsqueda case-insensitive sobre title/artist/album."""
    qlike = f"%{q.strip().lower()}%"
    visible_ids = access_svc.visible_track_ids_subquery(user)
    stmt = (
        select(Track, Artist, Album)
        .join(Artist, Track.artist_id == Artist.id)
        .outerjoin(Album, Track.album_id == Album.id)
        .where(Track.id.in_(visible_ids))
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
            "source_url": track.source_url,
        })
    return {"query": q, "total": len(items), "items": items}


# ─── Borrado y edición ────────────────────────────────────────


@router.delete("/tracks/{track_id}")
def delete_track(
    track_id: int,
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    t = session.get(Track, track_id)
    if not t:
        raise HTTPException(404, "track no encontrado")
    album = session.get(Album, t.album_id) if t.album_id else None
    if not access_svc.can_mutate_track(album, user):
        raise HTTPException(403, "no es tuyo")
    if not library_svc.delete_track(track_id):
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
def edit_track(
    track_id: int,
    body: EditTrackIn,
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    t = session.get(Track, track_id)
    if not t:
        raise HTTPException(404, "track no encontrado")
    album = session.get(Album, t.album_id) if t.album_id else None
    if not access_svc.can_mutate_track(album, user):
        raise HTTPException(403, "no es tuyo")
    # Si quiere mover a otro álbum, verificar que sea suyo
    if body.target_album_id:
        target = session.get(Album, body.target_album_id)
        if not target:
            raise HTTPException(400, "álbum destino no existe")
        if not access_svc.can_mutate_album(target, user):
            raise HTTPException(403, "no eres dueño del álbum destino")
    res = library_svc.edit_track(track_id, **body.model_dump(exclude_none=True))
    if not res.get("ok"):
        raise HTTPException(400, res.get("reason", "error"))
    return res


class NewAlbumIn(BaseModel):
    title: str
    artist: Optional[str] = None
    year: Optional[int] = None
    is_public: bool = False


@router.post("/albums")
def create_album(
    body: NewAlbumIn,
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Crea un álbum vacío. El user lo posee y decide si lo comparte."""
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(400, "título requerido")
    artist_name = (body.artist or "").strip() or "Various Artists"
    artist = library_svc._get_or_create_artist(session, artist_name)
    album = library_svc._get_or_create_album(session, title, artist.id, body.year)
    if album.owner_id is None:
        album.owner_id = user.id
    album.is_public = body.is_public
    session.add(album)
    session.flush()
    return {
        "id": album.id,
        "title": album.title,
        "artist_id": album.artist_id,
        "artist_name": artist.name,
        "year": album.year,
        "is_public": album.is_public,
        "owner_id": album.owner_id,
    }


@router.delete("/albums/{album_id}")
def delete_album(
    album_id: int,
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    a = session.get(Album, album_id)
    if not a:
        raise HTTPException(404, "no encontrado")
    if not access_svc.can_mutate_album(a, user):
        raise HTTPException(403, "no es tuyo")
    res = library_svc.delete_album(album_id)
    if not res.get("deleted"):
        raise HTTPException(404, res.get("reason", "no encontrado"))
    return res


class EditAlbumIn(BaseModel):
    title: Optional[str] = None
    year: Optional[int] = None
    is_public: Optional[bool] = None


@router.patch("/albums/{album_id}")
def edit_album(
    album_id: int,
    body: EditAlbumIn,
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    a = session.get(Album, album_id)
    if not a:
        raise HTTPException(404, "no encontrado")
    if not access_svc.can_mutate_album(a, user):
        raise HTTPException(403, "no es tuyo")
    # is_public lo gestionamos aquí, los demás campos vía library_svc.edit_album
    if body.is_public is not None:
        a.is_public = body.is_public
        session.add(a)
    edit_kwargs = body.model_dump(exclude_none=True)
    edit_kwargs.pop("is_public", None)
    if edit_kwargs:
        res = library_svc.edit_album(album_id, **edit_kwargs)
        if not res.get("ok"):
            raise HTTPException(400, res.get("reason", "error"))
    return {"ok": True, "is_public": a.is_public}


# ─── Letras (LRCLIB) ──────────────────────────────────────────


@router.get("/tracks/{track_id}/lyrics")
def get_lyrics(
    track_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(auth_svc.get_current_user),
) -> dict:
    t = session.get(Track, track_id)
    if not t:
        raise HTTPException(404, "track no encontrado")
    # Visibilidad
    album = session.get(Album, t.album_id) if t.album_id else None
    if album and not user.is_admin and not (album.is_public or album.owner_id == user.id):
        raise HTTPException(403, "no tienes acceso")
    artist = session.get(Artist, t.artist_id)
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
    user: User = Depends(auth_svc.get_current_user),
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
    # Asignar el álbum recién creado al uploader si no tiene owner
    if track_id:
        with library_svc.session_scope() as s:
            t = s.get(Track, track_id)
            if t and t.album_id:
                a = s.get(Album, t.album_id)
                if a and a.owner_id is None:
                    a.owner_id = user.id
                    s.add(a)
    return {
        "ok": True,
        "track_id": track_id,
        "title": meta.title,
        "artist": meta.primary_artist,
        "album": meta.album,
    }


@router.get("/stats")
def library_stats(
    session: Session = Depends(get_session),
    user: User = Depends(auth_svc.get_current_user),
) -> dict:
    """Stats con dos vistas:
    - mine: lo que este user puede ver (sus álbumes + públicos).
    - global: TODO lo que hay en la instancia, sin filtros.
    """
    # ─── mine ───
    visible_ids = access_svc.visible_track_ids_subquery(user)
    mine_tracks = session.exec(
        select(func.count()).select_from(select(Track).where(Track.id.in_(visible_ids)).subquery())
    ).one()
    mine_albums = len(access_svc.visible_album_ids(session, user))
    mine_artists = session.exec(
        select(func.count(func.distinct(Track.artist_id))).where(Track.id.in_(visible_ids))
    ).one()
    mine_bytes = session.exec(
        select(func.coalesce(func.sum(Track.file_size), 0)).where(Track.id.in_(visible_ids))
    ).one()

    # ─── global (sin filtros, todo el contenido del server) ───
    g_tracks = session.exec(select(func.count(Track.id))).one()
    g_albums = session.exec(select(func.count(Album.id))).one()
    g_artists = session.exec(select(func.count(Artist.id))).one()
    g_bytes = session.exec(select(func.coalesce(func.sum(Track.file_size), 0))).one()

    return {
        "mine": {
            "tracks": mine_tracks,
            "albums": mine_albums,
            "artists": mine_artists,
            "total_bytes": mine_bytes,
        },
        "global": {
            "tracks": g_tracks,
            "albums": g_albums,
            "artists": g_artists,
            "total_bytes": g_bytes,
        },
        # Compatibilidad con clientes viejos: aplanamos las del user
        "tracks": mine_tracks,
        "albums": mine_albums,
        "artists": mine_artists,
        "total_bytes": mine_bytes,
    }
