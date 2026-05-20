from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import jobs

router = APIRouter(tags=["ingest"])


class IngestRequest(BaseModel):
    url: str


@router.post("/ingest")
def ingest(req: IngestRequest) -> dict:
    try:
        return jobs.create_jobs_from_url(req.url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, f"error inesperado: {e}")
