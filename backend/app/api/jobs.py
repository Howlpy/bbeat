from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.models import User
from app.services import auth as auth_svc
from app.services import jobs as jobs_svc

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def list_jobs(
    limit: int = 100,
    user: User = Depends(auth_svc.get_current_user),
) -> dict:
    """Importaciones recientes de todo el servidor (con quién las lanzó).

    `stats` sigue siendo del propio usuario (admin: todo), porque cuelga de él
    el badge y los botones masivos; `stats_all` es el resumen de lo que se lista.
    Reintentar/borrar sigue limitado al dueño o admin.
    """
    items = jobs_svc.list_jobs(limit=limit)
    return {
        "total": len(items),
        "items": items,
        "stats": jobs_svc.job_stats(user_id=None if user.is_admin else user.id),
        "stats_all": jobs_svc.job_stats(),
    }


@router.get("/stats")
def stats(user: User = Depends(auth_svc.get_current_user)) -> dict:
    return jobs_svc.job_stats(user_id=None if user.is_admin else user.id)


@router.post("/retry-failed")
def retry_failed(user: User = Depends(auth_svc.get_current_user)) -> dict:
    n = jobs_svc.retry_all_failed(user_id=None if user.is_admin else user.id)
    return {"retried": n}


@router.delete("")
def clear_jobs(
    status: Optional[str] = Query(None),
    user: User = Depends(auth_svc.get_current_user),
) -> dict:
    deleted = jobs_svc.clear_jobs(status, user_id=None if user.is_admin else user.id)
    return {"deleted": deleted}


@router.post("/{job_id}/retry")
def retry(
    job_id: int,
    user: User = Depends(auth_svc.get_current_user),
) -> dict:
    if not jobs_svc.user_owns_job(job_id, user):
        raise HTTPException(403, "no es tuyo")
    ok = jobs_svc.retry_job(job_id)
    if not ok:
        raise HTTPException(400, "el job no existe o no está en estado failed")
    return {"ok": True}


@router.delete("/{job_id}")
def delete(
    job_id: int,
    user: User = Depends(auth_svc.get_current_user),
) -> dict:
    if not jobs_svc.user_owns_job(job_id, user):
        raise HTTPException(403, "no es tuyo")
    ok = jobs_svc.delete_job(job_id)
    if not ok:
        raise HTTPException(400, "no se pudo borrar (no existe o está en ejecución)")
    return {"ok": True}
