from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.models import User
from app.services import auth as auth_svc
from app.services import jobs
from app.services.jobs import IngestOverrides
from app.services.spotify import IngestError

router = APIRouter(tags=["ingest"])


class OverridesIn(BaseModel):
    album: Optional[str] = None
    artist: Optional[str] = None
    album_artist: Optional[str] = None
    year: Optional[int] = None
    cover_url: Optional[str] = None
    target_album_id: Optional[int] = None


class IngestRequest(BaseModel):
    url: str
    overrides: Optional[OverridesIn] = None
    # Si viene, solo se importan las pistas cuyo spotify_id esté en la lista
    # (para deseleccionar pistas de una playlist desde la UI).
    only_ids: Optional[list[str]] = None


def _to_dataclass(ov: Optional[OverridesIn]) -> Optional[IngestOverrides]:
    if ov is None:
        return None
    return IngestOverrides(**ov.model_dump(exclude_none=True))


@router.post("/ingest")
def ingest(
    req: IngestRequest,
    user: User = Depends(auth_svc.get_current_user),
) -> dict:
    try:
        return jobs.create_jobs_from_url(
            req.url,
            overrides=_to_dataclass(req.overrides),
            user_id=user.id,
            only_ids=req.only_ids,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except IngestError as e:
        raise HTTPException(422, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, f"error inesperado: {type(e).__name__}: {e}")


@router.post("/ingest/preview")
def ingest_preview(
    req: IngestRequest,
    _: User = Depends(auth_svc.get_current_user),
) -> dict:
    """Resuelve la URL sin crear jobs."""
    from app.services import sources, spotify, ytdlp_resolver

    url = req.url
    source = sources.detect(url)
    try:
        if source == "spotify":
            result = spotify.resolve_url(url)
        elif source in ("youtube", "soundcloud"):
            result = ytdlp_resolver.resolve_url(url, source)
        else:
            raise HTTPException(
                400,
                "URL no soportada. Acepto enlaces de Spotify, YouTube o SoundCloud.",
            )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except IngestError as e:
        raise HTTPException(422, str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"error inesperado: {type(e).__name__}: {e}")

    return {
        "source": source,
        "kind": result.kind,
        "name": result.name,
        "total_tracks": len(result.tracks),
        "tracks": [
            {
                "spotify_id": t.spotify_id,
                "title": t.title,
                "artists": t.artists,
                "album": t.album,
                "duration_ms": t.duration_ms,
                "cover_url": t.cover_url,
                "track_number": t.track_number,
            }
            for t in result.tracks
        ],
    }
