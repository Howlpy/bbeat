from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import jobs
from app.services.spotify import IngestError

router = APIRouter(tags=["ingest"])


class IngestRequest(BaseModel):
    url: str


@router.post("/ingest")
def ingest(req: IngestRequest) -> dict:
    try:
        return jobs.create_jobs_from_url(req.url)
    except ValueError as e:
        # URL malformada / no reconocida
        raise HTTPException(400, str(e))
    except IngestError as e:
        # URL bien formada pero Spotify no devuelve nada (404, privada, eliminada)
        raise HTTPException(422, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        # Caja negra final, dejamos el detalle para diagnóstico
        raise HTTPException(500, f"error inesperado: {type(e).__name__}: {e}")


@router.post("/ingest/preview")
def ingest_preview(req: IngestRequest) -> dict:
    """Resuelve la URL sin crear jobs todavía — útil para mostrar
    al usuario qué se va a importar antes de confirmar."""
    from app.services import spotify
    try:
        result = spotify.resolve_url(req.url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except IngestError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"error inesperado: {type(e).__name__}: {e}")
    return {
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
