from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.services import jobs as jobs_svc

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def list_jobs(limit: int = 100) -> dict:
    items = jobs_svc.list_jobs(limit=limit)
    return {
        "total": len(items),
        "items": items,
        "stats": jobs_svc.job_stats(),
    }


@router.get("/stats")
def stats() -> dict:
    return jobs_svc.job_stats()


@router.post("/retry-failed")
def retry_failed() -> dict:
    n = jobs_svc.retry_all_failed()
    return {"retried": n}


@router.delete("")
def clear_jobs(status: Optional[str] = Query(None, description="opcional: filtra por estado")) -> dict:
    deleted = jobs_svc.clear_jobs(status)
    return {"deleted": deleted}


@router.post("/{job_id}/retry")
def retry(job_id: int) -> dict:
    ok = jobs_svc.retry_job(job_id)
    if not ok:
        raise HTTPException(400, "el job no existe o no está en estado failed")
    return {"ok": True}


@router.delete("/{job_id}")
def delete(job_id: int) -> dict:
    ok = jobs_svc.delete_job(job_id)
    if not ok:
        raise HTTPException(400, "no se pudo borrar (no existe o está en ejecución)")
    return {"ok": True}
