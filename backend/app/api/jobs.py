from fastapi import APIRouter, HTTPException

from app.services import jobs as jobs_svc

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def list_jobs(limit: int = 100) -> dict:
    items = jobs_svc.list_jobs(limit=limit)
    return {"total": len(items), "items": items}


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
