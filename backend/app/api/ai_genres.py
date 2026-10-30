"""Admin: géneros con IA (estado, ejecución, revisión) y género por artista."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from app.db import get_session
from app.models import Artist, GenreSuggestion, Track, User
from app.services import auth as auth_svc
from app.services import genres as genres_svc
from app.services.ai import genre_ai

router = APIRouter(prefix="/admin", tags=["admin"])


class RunIn(BaseModel):
    limit: int = 25
    only_missing: bool = False


class GenreIn(BaseModel):
    genre: Optional[str] = None


@router.get("/ai-genres/status")
def ai_status(
    _: User = Depends(auth_svc.require_admin), session: Session = Depends(get_session)
) -> dict:
    without = session.exec(
        select(func.count(Track.id)).where(
            (Track.genre.is_(None)) | (func.trim(Track.genre) == "")
        )
    ).one()
    pending = session.exec(
        select(func.count(GenreSuggestion.id)).where(GenreSuggestion.status == "pending")
    ).one()
    candidates = len(genre_ai.candidate_artist_ids(session))
    return {
        "config": genre_ai.config_summary(),
        "tracks_without_genre": without,
        "pending_suggestions": pending,
        "unclassified_artists": candidates,
        "run": genre_ai.state.as_dict(),
    }


@router.post("/ai-genres/run")
def ai_run(body: RunIn, _: User = Depends(auth_svc.require_admin)) -> dict:
    if not genre_ai.is_enabled():
        raise HTTPException(400, "La IA no está configurada (BBEAT_AI_PROVIDER).")
    limit = max(1, min(body.limit, 500))
    started = genre_ai.start_background(limit=limit, only_missing=body.only_missing)
    return {"started": started, "run": genre_ai.state.as_dict()}


@router.post("/ai-genres/stop")
def ai_stop(_: User = Depends(auth_svc.require_admin)) -> dict:
    genre_ai.request_stop()
    return {"ok": True}


@router.get("/ai-genres/suggestions")
def list_suggestions(
    status: str = "pending",
    _: User = Depends(auth_svc.require_admin),
    session: Session = Depends(get_session),
) -> dict:
    rows = session.exec(
        select(GenreSuggestion, Artist.name, Track.title)
        .join(Artist, Artist.id == GenreSuggestion.artist_id)
        .outerjoin(Track, Track.id == GenreSuggestion.track_id)
        .where(GenreSuggestion.status == status, GenreSuggestion.genre.is_not(None))
        .order_by(Artist.name, GenreSuggestion.track_id.is_not(None), GenreSuggestion.id)
        .limit(500)
    ).all()
    return {
        "items": [
            {
                "id": s.id,
                "artist_id": s.artist_id,
                "artist_name": an,
                "track_id": s.track_id,
                "track_title": tt,
                "genre": s.genre,
                "genre_name": genres_svc.genre_label(s.genre),
                "previous_genre": s.previous_genre,
                "confidence": s.confidence,
                "reason": s.reason,
                "status": s.status,
            }
            for s, an, tt in rows
        ]
    }


@router.post("/ai-genres/suggestions/{sid}/accept")
def accept(
    sid: int,
    body: GenreIn,
    _: User = Depends(auth_svc.require_admin),
    session: Session = Depends(get_session),
) -> dict:
    try:
        n = genre_ai.accept_suggestion(session, sid, body.genre)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "changed": n}


@router.post("/ai-genres/suggestions/{sid}/reject")
def reject(
    sid: int,
    _: User = Depends(auth_svc.require_admin),
    session: Session = Depends(get_session),
) -> dict:
    try:
        genre_ai.reject_suggestion(session, sid)
    except LookupError as e:
        raise HTTPException(404, str(e))
    return {"ok": True}


@router.put("/artists/{artist_id}/genre")
def set_artist_genre(
    artist_id: int,
    body: GenreIn,
    _: User = Depends(auth_svc.require_admin),
    session: Session = Depends(get_session),
) -> dict:
    if session.get(Artist, artist_id) is None:
        raise HTTPException(404, "artista no encontrado")
    if not (body.genre or "").strip():
        raise HTTPException(400, "falta el género")
    return genre_ai.set_artist_genre(session, artist_id, body.genre)
