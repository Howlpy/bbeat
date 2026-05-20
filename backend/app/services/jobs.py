"""Cola de jobs de ingesta. Worker single-thread reactivo a un asyncio.Event."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from sqlmodel import select

from app.db import session_scope
from app.models import Job
from app.services import downloader, organizer, scanner, spotify

log = logging.getLogger("bbeat.jobs")


_wake_event: Optional[asyncio.Event] = None
_worker_task: Optional[asyncio.Task] = None


def _get_wake_event() -> asyncio.Event:
    global _wake_event
    if _wake_event is None:
        _wake_event = asyncio.Event()
    return _wake_event


def wake() -> None:
    """Despierta al worker. Llámalo tras crear jobs nuevos."""
    ev = _get_wake_event()
    ev.set()


# ─── Creación de jobs desde URL ────────────────────────────────


def create_jobs_from_url(url: str) -> dict:
    """Resuelve la URL con Spotipy y crea N Jobs en BD. Devuelve resumen."""
    result = spotify.resolve_url(url)
    created: list[int] = []
    skipped: list[str] = []

    with session_scope() as session:
        for meta in result.tracks:
            existing = session.exec(
                select(Job).where(Job.spotify_track_id == meta.spotify_id)
            ).first()
            if existing and existing.status in ("pending", "running", "done"):
                skipped.append(meta.spotify_id)
                continue
            job = Job(
                source_url=url,
                source_kind=result.kind,
                spotify_track_id=meta.spotify_id,
                title=meta.title,
                artist=meta.primary_artist,
                artists_csv=", ".join(meta.artists),
                album_artist=meta.album_artist,
                album=meta.album,
                track_number=meta.track_number,
                disc_number=meta.disc_number,
                total_tracks=meta.total_tracks,
                duration_ms=meta.duration_ms,
                year=meta.year,
                cover_url=meta.cover_url,
                status="pending",
            )
            session.add(job)
            session.flush()
            created.append(job.id)

    wake()
    return {
        "kind": result.kind,
        "name": result.name,
        "total_tracks": len(result.tracks),
        "created_job_ids": created,
        "skipped_track_ids": skipped,
    }


# ─── Pipeline de un job ────────────────────────────────────────


def _load_meta_from_job(job: Job) -> spotify.TrackMeta:
    """Reconstruye TrackMeta desde el Job (info ya capturada al crearlo)."""
    artists = [a.strip() for a in (job.artists_csv or job.artist or "").split(",") if a.strip()]
    return spotify.TrackMeta(
        spotify_id=job.spotify_track_id,
        title=job.title,
        artists=artists,
        album=job.album,
        album_artist=job.album_artist or (artists[0] if artists else ""),
        track_number=job.track_number,
        disc_number=job.disc_number,
        total_tracks=job.total_tracks,
        duration_ms=job.duration_ms or 0,
        isrc=None,
        year=job.year,
        cover_url=job.cover_url,
        source_url=job.source_url,
        source_kind=job.source_kind,
    )


def process_job(job_id: int) -> None:
    """Ejecuta el pipeline completo para un job. Síncrono (bloqueante)."""
    with session_scope() as s:
        job = s.get(Job, job_id)
        if not job:
            return
        job.status = "running"
        job.started_at = datetime.utcnow()
        job.error = None
        s.add(job)

    try:
        meta = _load_meta_for_job_safe(job_id)
        if meta is None:
            return

        dl_result = downloader.download(meta)
        if not dl_result.success:
            _mark_failed(job_id, dl_result.backend, dl_result.error or "download failed")
            return

        # Organize
        try:
            final_path = organizer.organize(dl_result.file_path, meta)
        except Exception as e:
            log.exception("organize falló")
            _mark_failed(job_id, dl_result.backend, f"organize: {e}")
            return

        # Index en BD
        track_id = scanner.index_file(final_path)

        with session_scope() as s:
            job = s.get(Job, job_id)
            if job:
                job.status = "done"
                job.backend_used = dl_result.backend
                job.result_track_id = track_id
                job.completed_at = datetime.utcnow()
                s.add(job)
        log.info("job %s OK · %s · %s", job_id, dl_result.backend, final_path.name)
    except Exception as e:
        log.exception("job %s: error inesperado", job_id)
        _mark_failed(job_id, None, str(e))


def _load_meta_for_job_safe(job_id: int) -> Optional[spotify.TrackMeta]:
    with session_scope() as s:
        job = s.get(Job, job_id)
        if not job:
            return None
        return _load_meta_from_job(job)


def _mark_failed(job_id: int, backend: Optional[str], error: str) -> None:
    with session_scope() as s:
        job = s.get(Job, job_id)
        if job:
            job.status = "failed"
            job.backend_used = backend
            job.error = error[:1000]
            job.completed_at = datetime.utcnow()
            s.add(job)
    log.warning("job %s FAILED: %s", job_id, error)


def retry_job(job_id: int) -> bool:
    with session_scope() as s:
        job = s.get(Job, job_id)
        if not job or job.status != "failed":
            return False
        job.status = "pending"
        job.error = None
        job.started_at = None
        job.completed_at = None
        s.add(job)
    wake()
    return True


def delete_job(job_id: int) -> bool:
    with session_scope() as s:
        job = s.get(Job, job_id)
        if not job:
            return False
        if job.status == "running":
            return False  # no cancelamos durante ejecución (MVP)
        s.delete(job)
        return True


# ─── Worker loop ───────────────────────────────────────────────


async def _worker_loop() -> None:
    log.info("worker arrancado")
    ev = _get_wake_event()
    while True:
        # Coger el siguiente pendiente
        with session_scope() as s:
            job = s.exec(
                select(Job).where(Job.status == "pending").order_by(Job.created_at)
            ).first()
            job_id = job.id if job else None

        if job_id is not None:
            await asyncio.to_thread(process_job, job_id)
        else:
            # No hay nada: esperar a wake() o un tick periódico de seguridad
            try:
                await asyncio.wait_for(ev.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass
            ev.clear()


def start_worker() -> None:
    global _worker_task
    if _worker_task is not None and not _worker_task.done():
        return
    loop = asyncio.get_event_loop()
    _worker_task = loop.create_task(_worker_loop())


# ─── Listados para la UI ───────────────────────────────────────


def list_jobs(limit: int = 100) -> list[dict]:
    with session_scope() as s:
        rows = s.exec(select(Job).order_by(Job.created_at.desc()).limit(limit)).all()
        return [_job_to_dict(j) for j in rows]


def _job_to_dict(j: Job) -> dict:
    return {
        "id": j.id,
        "source_url": j.source_url,
        "source_kind": j.source_kind,
        "spotify_track_id": j.spotify_track_id,
        "title": j.title,
        "artist": j.artist,
        "album": j.album,
        "album_artist": j.album_artist,
        "track_number": j.track_number,
        "disc_number": j.disc_number,
        "total_tracks": j.total_tracks,
        "duration_ms": j.duration_ms,
        "year": j.year,
        "cover_url": j.cover_url,
        "status": j.status,
        "backend_used": j.backend_used,
        "error": j.error,
        "result_track_id": j.result_track_id,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "completed_at": j.completed_at.isoformat() if j.completed_at else None,
    }
