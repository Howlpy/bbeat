import asyncio
import json
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.config import settings
from app.db import get_session
from app.models import Album, AlbumSave, AlbumTrack, Artist, Play, Track, TrackLike, User
from app.services import access as access_svc
from app.services import auth as auth_svc
from app.services import library as library_svc
from app.services import lyrics as lyrics_svc
from app.services import organizer, presence as presence_svc, scanner, spotify

router = APIRouter(prefix="/library", tags=["library"])


def _cover_ver(filename: Optional[str]) -> str:
    """Sufijo ?v=<mtime> para versionar la URL de una carátula. Cuando el fichero
    cambia (re-subida), cambia la URL → cualquier caché (navegador/CDN) la refresca.
    """
    if not filename:
        return ""
    try:
        return f"?v={int((settings.covers_dir / filename).stat().st_mtime)}"
    except OSError:
        return ""


def _track_cover_file(track_id: int) -> Optional[str]:
    for ext in (".jpg", ".png"):
        if (settings.covers_dir / f"track-{track_id}{ext}").is_file():
            return f"track-{track_id}{ext}"
    return None


def _user_liked_set(session: Session, user: User) -> set[int]:
    """track_ids a los que este usuario ha dado 'me gusta'."""
    rows = session.exec(select(TrackLike.track_id).where(TrackLike.user_id == user.id)).all()
    return {r[0] if isinstance(r, (tuple, list)) else r for r in rows}


def _user_saved_album_ids(session: Session, user: User) -> set[int]:
    """album_ids que este usuario ha guardado en su biblioteca."""
    rows = session.exec(select(AlbumSave.album_id).where(AlbumSave.user_id == user.id)).all()
    return {r[0] if isinstance(r, (tuple, list)) else r for r in rows}


def _album_payload(
    album: Album, artist_name: str, track_count: int, *, is_saved: bool, is_mine: bool
) -> dict:
    """Dict serializado de un álbum/playlist para la UI (formato único)."""
    return {
        "id": album.id,
        "title": album.title,
        "year": album.year,
        "artist_id": album.artist_id,
        "artist_name": artist_name,
        "track_count": track_count,
        "cover_url": (
            f"/api/library/cover/{album.id}{_cover_ver(album.cover_path)}"
            if album.cover_path
            else None
        ),
        "owner_id": album.owner_id,
        "kind": album.kind,
        "is_mine": is_mine,
        "is_saved": is_saved,
    }


def _track_payload(track: Track, artist: Artist, album: Optional[Album], liked: bool = False) -> dict:
    """Dict serializado de una pista para la UI (formato único compartido)."""
    return {
        "id": track.id,
        "title": track.title,
        "artist_id": artist.id,
        "artist_name": artist.name,
        "album_id": album.id if album else None,
        "album_title": album.title if album else None,
        "album_year": album.year if album else None,
        "cover_url": (
            f"/api/library/cover/track/{track.id}{_cover_ver(_track_cover_file(track.id))}"
            if getattr(track, "has_cover", False)
            else (
                f"/api/library/cover/{album.id}{_cover_ver(album.cover_path)}"
                if album and album.cover_path
                else None
            )
        ),
        "track_number": track.track_number,
        "disc_number": track.disc_number,
        "duration_ms": track.duration_ms,
        "file_format": track.file_format,
        "stream_url": f"/api/library/stream/{track.id}",
        "source_url": track.source_url,
        "liked": liked,
    }


@router.get("/tracks")
def list_tracks(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    artist_id: Optional[int] = None,
    album_id: Optional[int] = None,
    session: Session = Depends(get_session),
    user: User = Depends(auth_svc.get_current_user),
) -> dict:
    # Pool global: cualquier usuario ve todas las pistas del server, estén o no
    # en un álbum suyo/público. La privacidad de álbumes solo aplica a mutar.
    stmt = (
        select(Track, Artist, Album)
        .join(Artist, Track.artist_id == Artist.id)
        .outerjoin(Album, Track.album_id == Album.id)
    )
    count_stmt = select(func.count(Track.id)).select_from(Track)
    if artist_id is not None:
        stmt = stmt.where(Track.artist_id == artist_id)
        count_stmt = count_stmt.where(Track.artist_id == artist_id)
    if album_id is not None:
        # Vía AlbumTrack (M:N): incluye tracks que pertenecen al álbum aunque
        # su album_id "primario" sea otro.
        in_album_subq = select(AlbumTrack.track_id).where(AlbumTrack.album_id == album_id)
        stmt = stmt.where(Track.id.in_(in_album_subq))
        count_stmt = count_stmt.where(Track.id.in_(in_album_subq))
    total = session.exec(count_stmt).one()

    stmt = stmt.order_by(Album.title, Track.disc_number, Track.track_number, Track.title)
    stmt = stmt.limit(limit).offset(offset)

    liked = _user_liked_set(session, user)
    items = [
        _track_payload(track, artist, album, track.id in liked)
        for track, artist, album in session.exec(stmt).all()
    ]
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@router.get("/albums")
def list_albums(
    scope: str = Query("saved", regex="^(saved|all|mine)$"),
    kind: Optional[str] = Query(None, regex="^(album|playlist)$"),
    q: Optional[str] = Query(None),
    session: Session = Depends(get_session),
    user: User = Depends(auth_svc.get_current_user),
) -> dict:
    """Lista álbumes/playlists. scope: 'saved' (los que guardaste, por defecto),
    'all' (explorar todo el catálogo) o 'mine' (de los que eres dueño)."""
    saved_ids = _user_saved_album_ids(session, user)
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
    if scope == "saved":
        if not saved_ids:
            return {"total": 0, "items": []}
        stmt = stmt.where(Album.id.in_(saved_ids))
    elif scope == "mine":
        stmt = stmt.where(Album.owner_id == user.id)
    # 'all' → pool global, sin filtro de propiedad.
    if kind:
        stmt = stmt.where(Album.kind == kind)
    if q and q.strip():
        qlike = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(func.lower(Album.title).like(qlike), func.lower(Artist.name).like(qlike))
        )
    items = [
        _album_payload(
            album, artist_name, track_count,
            is_saved=album.id in saved_ids,
            is_mine=album.owner_id == user.id,
        )
        for album, artist_name, track_count in session.exec(stmt).all()
    ]
    return {"total": len(items), "items": items}


@router.put("/albums/{album_id}/save")
def save_album(
    album_id: int,
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Guarda un álbum/playlist en tu biblioteca (aparece en 'Guardados')."""
    if not session.get(Album, album_id):
        raise HTTPException(404, "álbum no encontrado")
    if not session.get(AlbumSave, (user.id, album_id)):
        session.add(AlbumSave(user_id=user.id, album_id=album_id))
    return {"saved": True}


@router.delete("/albums/{album_id}/save")
def unsave_album(
    album_id: int,
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Quita un álbum/playlist de tu biblioteca (no borra nada del catálogo)."""
    existing = session.get(AlbumSave, (user.id, album_id))
    if existing:
        session.delete(existing)
    return {"saved": False}


@router.get("/albums/{album_id}")
def get_album(
    album_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(auth_svc.get_current_user),
) -> dict:
    """Un álbum/playlist concreto (para la vista de detalle, lo veas o no guardado)."""
    album = session.get(Album, album_id)
    if not album:
        raise HTTPException(404, "álbum no encontrado")
    artist = session.get(Artist, album.artist_id)
    track_count = session.exec(
        select(func.count(AlbumTrack.track_id)).where(AlbumTrack.album_id == album_id)
    ).one()
    return _album_payload(
        album,
        artist.name if artist else "Unknown Artist",
        track_count,
        is_saved=session.get(AlbumSave, (user.id, album_id)) is not None,
        is_mine=album.owner_id == user.id,
    )


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
    import logging
    from app.models import AlbumTrack

    log = logging.getLogger("bbeat.library")

    album = session.get(Album, album_id)
    if album is None:
        raise HTTPException(404, "álbum no encontrado")
    if not access_svc.can_mutate_album(album, user):
        raise HTTPException(403, "no es tuyo")

    if not body.track_ids:
        return {"added": 0, "already": 0, "denied": 0}

    # Filtra a los track_ids que el user realmente puede ver
    visible_subq = access_svc.visible_track_ids_subquery(user)
    allowed_rows = session.exec(
        select(Track.id).where(Track.id.in_(body.track_ids)).where(Track.id.in_(visible_subq))
    ).all()
    # SQLModel devuelve directamente los IDs como int, pero por si acaso unión devuelve tuplas
    allowed_ids = {r[0] if isinstance(r, (tuple, list)) else r for r in allowed_rows}

    # IDs ya en este álbum
    existing_rows = session.exec(
        select(AlbumTrack.track_id).where(
            AlbumTrack.album_id == album_id,
            AlbumTrack.track_id.in_(body.track_ids),
        )
    ).all()
    existing_ids = {r[0] if isinstance(r, (tuple, list)) else r for r in existing_rows}

    added = 0
    already = 0
    denied = 0
    for tid in body.track_ids:
        if tid in existing_ids:
            already += 1
            continue
        if tid not in allowed_ids:
            denied += 1
            continue
        session.add(AlbumTrack(album_id=album_id, track_id=tid))
        added += 1

    log.info(
        "add_tracks album=%s by user=%s: added=%d already=%d denied=%d",
        album_id, user.id, added, already, denied,
    )
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
    liked = _user_liked_set(session, user)
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
                **_track_payload(t, ar, al, t.id in liked),
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t, ar, al in session.exec(stmt).all()
        ]
    if kind in ("albums", "both"):
        saved_ids = _user_saved_album_ids(session, user)
        stmt = (
            select(Album, Artist.name, func.count(AlbumTrack.track_id).label("tc"))
            .join(Artist, Album.artist_id == Artist.id)
            .outerjoin(AlbumTrack, AlbumTrack.album_id == Album.id)
            .group_by(Album.id)
            .order_by(Album.created_at.desc())
            .limit(limit)
        )
        out["albums"] = [
            _album_payload(
                a, an, tc, is_saved=a.id in saved_ids, is_mine=a.owner_id == user.id
            )
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
    """Búsqueda case-insensitive sobre title/artist/album. Pool global."""
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
    liked = _user_liked_set(session, user)
    items = [
        _track_payload(track, artist, album, track.id in liked)
        for track, artist, album in session.exec(stmt).all()
    ]
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
    kind: str = "playlist"


@router.post("/albums")
def create_album(
    body: NewAlbumIn,
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Crea una colección vacía. El user la posee y queda guardada en su biblioteca.

    Por defecto es 'playlist' (colección multi-artista hecha a mano)."""
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(400, "título requerido")
    artist_name = (body.artist or "").strip() or "Various Artists"
    artist = library_svc._get_or_create_artist(session, artist_name)
    album = library_svc._get_or_create_album(session, title, artist.id, body.year)
    if album.owner_id is None:
        album.owner_id = user.id
    album.kind = body.kind if body.kind in ("album", "playlist") else "playlist"
    session.add(album)
    session.flush()
    # Lo creas → lo tienes guardado.
    if not session.get(AlbumSave, (user.id, album.id)):
        session.add(AlbumSave(user_id=user.id, album_id=album.id))
    return _album_payload(
        album, artist.name, 0, is_saved=True, is_mine=album.owner_id == user.id
    )


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
    edit_kwargs = body.model_dump(exclude_none=True)
    if edit_kwargs:
        res = library_svc.edit_album(album_id, **edit_kwargs)
        if not res.get("ok"):
            raise HTTPException(400, res.get("reason", "error"))
    return {"ok": True}


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
    # Pool global: cualquier usuario autenticado puede pedir letras.
    album = session.get(Album, t.album_id) if t.album_id else None
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
    title: Optional[str] = Form(None),
    album: Optional[str] = Form(None),
    artist: Optional[str] = Form(None),
    year: Optional[int] = Form(None),
    target_album_id: Optional[int] = Form(None),
    as_single: bool = Form(False),
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
    detected_title = (title or "").strip() or _first("title") or Path(file.filename or "").stem

    if as_single and target_album_id:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(400, "una canción suelta no puede tener álbum destino")

    meta = spotify.TrackMeta(
        spotify_id=f"upload:{uuid.uuid4().hex[:12]}",
        title=detected_title,
        artists=[artist or detected_artist],
        # as_single fuerza album vacío incluso cuando el MP3 trae tags ID3.
        # organizer.write_tags eliminará album/albumartist/tracknumber antes
        # de que scanner lo indexe con album_id=None.
        album="" if as_single else (album if album is not None else detected_album) or "",
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


# ─── Me gusta (favoritos) ─────────────────────────────────────


@router.put("/tracks/{track_id}/like")
def like_track(
    track_id: int,
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    if not session.get(Track, track_id):
        raise HTTPException(404, "track no encontrado")
    if not session.get(TrackLike, (user.id, track_id)):
        session.add(TrackLike(user_id=user.id, track_id=track_id))
    return {"liked": True}


@router.delete("/tracks/{track_id}/like")
def unlike_track(
    track_id: int,
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    existing = session.get(TrackLike, (user.id, track_id))
    if existing:
        session.delete(existing)
    return {"liked": False}


@router.get("/liked")
def list_liked(
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Pistas a las que el usuario dio 'me gusta', recientes primero."""
    stmt = (
        select(Track, Artist, Album, TrackLike.created_at)
        .join(TrackLike, TrackLike.track_id == Track.id)
        .join(Artist, Track.artist_id == Artist.id)
        .outerjoin(Album, Track.album_id == Album.id)
        .where(TrackLike.user_id == user.id)
        .order_by(TrackLike.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [
        {**_track_payload(t, ar, al, True), "liked_at": liked_at.isoformat() if liked_at else None}
        for t, ar, al, liked_at in session.exec(stmt).all()
    ]
    total = session.exec(
        select(func.count()).select_from(TrackLike).where(TrackLike.user_id == user.id)
    ).one()
    return {"total": total, "items": items}


# ─── Historial + más escuchadas ───────────────────────────────


@router.post("/tracks/{track_id}/play")
def record_play(
    track_id: int,
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Registra una reproducción (el front lo llama al empezar cada pista)."""
    if not session.get(Track, track_id):
        raise HTTPException(404, "track no encontrado")
    session.add(Play(user_id=user.id, track_id=track_id))
    return {"ok": True}


# ─── Sonando ahora (presencia en vivo) ────────────────────────


def track_payload_by_id(session: Session, track_id: int, user: User) -> Optional[dict]:
    """Resuelve el payload de UI de una pista por id (o None si no existe).

    Reutilizable desde la API Subsonic para registrar presencia con el mismo
    formato que consume el feed `/live`.
    """
    row = session.exec(
        select(Track, Artist, Album)
        .join(Artist, Track.artist_id == Artist.id)
        .outerjoin(Album, Track.album_id == Album.id)
        .where(Track.id == track_id)
    ).first()
    if not row:
        return None
    track, artist, album = row
    liked = track_id in _user_liked_set(session, user)
    return _track_payload(track, artist, album, liked)


class NowPlayingIn(BaseModel):
    track_id: int


@router.post("/now-playing")
def now_playing_ping(
    body: NowPlayingIn,
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Heartbeat del player web: 'estoy escuchando esta pista ahora mismo'."""
    payload = track_payload_by_id(session, body.track_id, user)
    if not payload:
        raise HTTPException(404, "track no encontrado")
    presence_svc.touch(user.id, user.username, payload, "web", presence_svc.TTL_WEB)
    return {"ok": True}


@router.delete("/now-playing")
def now_playing_stop(
    user: User = Depends(auth_svc.get_current_user),
) -> dict:
    """El player web paró/pausó: salir del feed en vivo."""
    presence_svc.clear(user.id)
    return {"ok": True}


@router.get("/now-playing/stream")
async def now_playing_stream(
    request: Request,
    user: User = Depends(auth_svc.get_current_user),
) -> StreamingResponse:
    """Feed SSE de 'sonando ahora' en el server (todos los usuarios).

    Emite la lista completa de presencias cada vez que cambia; entre cambios
    manda un comentario keepalive para que la conexión no muera tras proxies.
    Autentica vía `?token=` (EventSource no puede mandar cabeceras).
    """

    async def event_stream():
        last = None
        idle = 0
        # Snapshot inicial nada más conectar.
        while True:
            if await request.is_disconnected():
                break
            items = presence_svc.snapshot()
            serialized = json.dumps(items, ensure_ascii=False, sort_keys=True)
            if serialized != last:
                last = serialized
                idle = 0
                yield f"data: {serialized}\n\n"
            else:
                idle += 1
                if idle >= 7:  # ~14s sin cambios → keepalive
                    idle = 0
                    yield ": keepalive\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/top")
def top_tracks(
    limit: int = Query(20, ge=1, le=100),
    days: Optional[int] = Query(None, ge=1, le=3650),
    scope: str = Query("me", regex="^(me|server)$"),
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Más escuchadas. scope=me (este usuario) o server (todo el servidor)."""
    plays = func.count(Play.id).label("plays")
    stmt = (
        select(Track, Artist, Album, plays)
        .join(Play, Play.track_id == Track.id)
        .join(Artist, Track.artist_id == Artist.id)
        .outerjoin(Album, Track.album_id == Album.id)
    )
    if scope == "me":
        stmt = stmt.where(Play.user_id == user.id)
    if days:
        stmt = stmt.where(Play.played_at >= datetime.utcnow() - timedelta(days=days))
    stmt = stmt.group_by(Track.id).order_by(plays.desc()).limit(limit)
    liked = _user_liked_set(session, user)
    items = [
        {**_track_payload(t, ar, al, t.id in liked), "plays": n}
        for t, ar, al, n in session.exec(stmt).all()
    ]
    return {"items": items}


@router.get("/history")
def play_history(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Pistas escuchadas recientemente (una entrada por pista, último play)."""
    last_played = func.max(Play.played_at).label("last_played")
    stmt = (
        select(Track, Artist, Album, last_played)
        .join(Play, Play.track_id == Track.id)
        .join(Artist, Track.artist_id == Artist.id)
        .outerjoin(Album, Track.album_id == Album.id)
        .where(Play.user_id == user.id)
        .group_by(Track.id)
        .order_by(last_played.desc())
        .limit(limit)
    )
    liked = _user_liked_set(session, user)
    items = [
        {**_track_payload(t, ar, al, t.id in liked), "last_played": lp.isoformat() if lp else None}
        for t, ar, al, lp in session.exec(stmt).all()
    ]
    return {"items": items}


@router.get("/me/stats")
def my_stats(
    days: Optional[int] = Query(None, ge=1, le=3650),
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Resumen tipo 'Wrapped' del usuario: totales + top tracks/artistas/álbumes."""
    cutoff = datetime.utcnow() - timedelta(days=days) if days else None

    def _scoped(stmt):
        stmt = stmt.where(Play.user_id == user.id)
        return stmt.where(Play.played_at >= cutoff) if cutoff else stmt

    total_plays = session.exec(_scoped(select(func.count(Play.id)))).one()
    total_ms = session.exec(
        _scoped(
            select(func.coalesce(func.sum(Track.duration_ms), 0))
            .select_from(Play)
            .join(Track, Track.id == Play.track_id)
        )
    ).one()
    unique_tracks = session.exec(_scoped(select(func.count(func.distinct(Play.track_id))))).one()

    liked = _user_liked_set(session, user)
    plays_lbl = func.count(Play.id).label("plays")

    tt = (
        select(Track, Artist, Album, plays_lbl)
        .join(Play, Play.track_id == Track.id)
        .join(Artist, Track.artist_id == Artist.id)
        .outerjoin(Album, Track.album_id == Album.id)
        .where(Play.user_id == user.id)
    )
    if cutoff:
        tt = tt.where(Play.played_at >= cutoff)
    tt = tt.group_by(Track.id).order_by(plays_lbl.desc()).limit(5)
    top_tracks = [
        {**_track_payload(t, ar, al, t.id in liked), "plays": n}
        for t, ar, al, n in session.exec(tt).all()
    ]

    ta = (
        select(Artist.id, Artist.name, plays_lbl)
        .join(Track, Track.artist_id == Artist.id)
        .join(Play, Play.track_id == Track.id)
        .where(Play.user_id == user.id)
    )
    if cutoff:
        ta = ta.where(Play.played_at >= cutoff)
    ta = ta.group_by(Artist.id).order_by(plays_lbl.desc()).limit(5)
    top_artists = [
        {"id": aid, "name": name, "plays": n} for aid, name, n in session.exec(ta).all()
    ]

    # Reloj de escucha: plays por hora del día (0-23), dentro del rango.
    clock = [0] * 24
    clock_rows = session.exec(
        _scoped(select(func.strftime("%H", Play.played_at), func.count(Play.id)))
        .group_by(func.strftime("%H", Play.played_at))
    ).all()
    for h, c in clock_rows:
        try:
            clock[int(h)] = c
        except (TypeError, ValueError):
            pass

    # Primer y último play (siempre histórico, no acotado por el rango).
    first_played, last_played = session.exec(
        select(func.min(Play.played_at), func.max(Play.played_at)).where(Play.user_id == user.id)
    ).one()

    def _iso(v):
        if v is None:
            return None
        return v.isoformat() if hasattr(v, "isoformat") else str(v)

    # Racha: días UTC consecutivos con ≥1 play, terminando hoy (o ayer si aún no
    # has escuchado nada hoy, para no romper una racha todavía viva).
    day_rows = session.exec(
        select(func.distinct(func.date(Play.played_at))).where(Play.user_id == user.id)
    ).all()
    days_set = {(r[0] if isinstance(r, (tuple, list)) else r) for r in day_rows}
    today = datetime.utcnow().date()
    cursor = today if today.isoformat() in days_set else today - timedelta(days=1)
    streak_days = 0
    while cursor.isoformat() in days_set:
        streak_days += 1
        cursor -= timedelta(days=1)

    # Comparativa con el periodo anterior de igual longitud (solo si hay rango).
    prev = None
    if cutoff is not None:
        prev_cut = cutoff - timedelta(days=days)

        def _prev(stmt):
            return stmt.where(
                Play.user_id == user.id,
                Play.played_at >= prev_cut,
                Play.played_at < cutoff,
            )

        prev_plays = session.exec(_prev(select(func.count(Play.id)))).one()
        prev_ms = session.exec(
            _prev(
                select(func.coalesce(func.sum(Track.duration_ms), 0))
                .select_from(Play)
                .join(Track, Track.id == Play.track_id)
            )
        ).one()
        prev = {"plays": prev_plays, "minutes": round((prev_ms or 0) / 60000)}

    return {
        "total_plays": total_plays,
        "total_minutes": round((total_ms or 0) / 60000),
        "unique_tracks": unique_tracks,
        "liked_count": len(liked),
        "top_tracks": top_tracks,
        "top_artists": top_artists,
        "clock": clock,
        "streak_days": streak_days,
        "first_play": _iso(first_played),
        "last_play": _iso(last_played),
        "prev": prev,
    }


@router.get("/activity")
def activity(
    limit: int = Query(30, ge=1, le=100),
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Reproducciones recientes de TODOS los usuarios (qué suena en el server)."""
    stmt = (
        select(Play.played_at, User.username, Track, Artist, Album)
        .join(User, User.id == Play.user_id)
        .join(Track, Track.id == Play.track_id)
        .join(Artist, Track.artist_id == Artist.id)
        .outerjoin(Album, Track.album_id == Album.id)
        .order_by(Play.played_at.desc())
        .limit(limit)
    )
    liked = _user_liked_set(session, user)
    items = [
        {
            "username": username,
            "played_at": played_at.isoformat() if played_at else None,
            **_track_payload(t, ar, al, t.id in liked),
        }
        for played_at, username, t, ar, al in session.exec(stmt).all()
    ]
    return {"items": items}
