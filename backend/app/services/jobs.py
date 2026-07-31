"""Cola de jobs de ingesta. Worker single-thread reactivo a un asyncio.Event."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Optional

from dataclasses import dataclass

from sqlmodel import select

from app.db import session_scope
from app.models import Album, AlbumSave, AlbumTrack, Artist, Job, Track
from app.services import downloader, library as library_svc, organizer, scanner, sources, spotify, ytdlp_resolver

log = logging.getLogger("bbeat.jobs")


def _yt_video_id(url: str) -> Optional[str]:
    """Extrae el id de un vídeo de YouTube de una URL (watch?v= o youtu.be/)."""
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else None


@dataclass
class IngestOverrides:
    album: Optional[str] = None
    artist: Optional[str] = None
    album_artist: Optional[str] = None
    year: Optional[int] = None
    cover_url: Optional[str] = None
    target_album_id: Optional[int] = None


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


def _resolve_any(url: str):
    """Despacha la URL al resolver correcto según la plataforma detectada."""
    source = sources.detect(url)
    if source == "spotify":
        return spotify.resolve_url(url), source
    if source in ("youtube", "soundcloud"):
        return ytdlp_resolver.resolve_url(url, source), source
    raise ValueError(
        "URL no soportada. Acepto enlaces de Spotify, YouTube o SoundCloud."
    )


def _apply_overrides(
    meta: spotify.TrackMeta,
    ov: Optional[IngestOverrides],
    *,
    apply_track_artist: bool = True,
) -> spotify.TrackMeta:
    if ov is None:
        return meta

    # target_album_id: si el usuario eligió un álbum existente, cogemos su info
    if ov.target_album_id:
        with session_scope() as s:
            album = s.get(Album, ov.target_album_id)
            if album:
                meta.album = album.title
                artist = s.get(Artist, album.artist_id)
                if artist:
                    meta.album_artist = artist.name
                    if not meta.artists:
                        meta.artists = [artist.name]
                if album.year:
                    meta.year = album.year

    # Overrides explícitos pisan a target_album_id
    if ov.album is not None:
        meta.album = ov.album
    if ov.album_artist is not None:
        meta.album_artist = ov.album_artist
    elif not apply_track_artist and ov.artist is not None:
        # Compatibilidad con clientes antiguos: en una playlist, el campo
        # "artist" representa al artista de la colección, nunca debe borrar el
        # artista real de cada pista.
        meta.album_artist = ov.artist
    if apply_track_artist and ov.artist is not None:
        meta.artists = [ov.artist] + [a for a in meta.artists if a != ov.artist]
    if ov.year is not None:
        meta.year = ov.year
    if ov.cover_url is not None:
        meta.cover_url = ov.cover_url
    return meta


def _resolve_target_album(
    session,
    overrides: Optional[IngestOverrides],
    user_id: Optional[int],
    meta: spotify.TrackMeta,
    source_kind: str = "track",
) -> Optional[int]:
    """Determina el álbum destino para una pista a partir de los overrides.

    - target_album_id: usa ese (si el user es dueño o admin).
    - overrides.album: crea-o-busca un álbum con ese nombre owned por user_id.
    - Si no hay overrides ni álbum natural: None (queda fuera de cualquier
      colección user-managed, solo va al álbum natural del scanner).
    """
    if overrides and overrides.target_album_id:
        return overrides.target_album_id
    if overrides and overrides.album and user_id:
        # crear/obtener album propio
        artist_name = overrides.album_artist or overrides.artist or meta.album_artist or meta.primary_artist
        artist = library_svc._get_or_create_artist(session, artist_name)
        year = overrides.year if overrides.year is not None else meta.year
        album = library_svc._get_or_create_album(session, overrides.album, artist.id, year)
        if source_kind == "playlist":
            album.kind = "playlist"
        if album.owner_id is None:
            album.owner_id = user_id
            session.add(album)
        return album.id
    return None


def _ensure_album_save(session, user_id: Optional[int], album_id: Optional[int]) -> None:
    """Auto-guarda el álbum en la biblioteca del usuario (idempotente)."""
    if not user_id or not album_id:
        return
    if not session.get(AlbumSave, (user_id, album_id)):
        session.add(AlbumSave(user_id=user_id, album_id=album_id))


def _collection_album_for_playlist(
    session, name: str, tracks: list[spotify.TrackMeta], user_id: int
) -> tuple[int, str]:
    """Crea/obtiene la colección (kind=playlist) que agrupa una playlist entera.

    El artista del álbum es 'Various Artists' salvo que TODAS las pistas sean del
    mismo artista. Devuelve (album_id, nombre_artista_de_album). La cuenta se
    auto-guarda para el usuario."""
    distinct = {(m.primary_artist or "").strip().lower() for m in tracks if m.primary_artist}
    coll_artist_name = tracks[0].primary_artist if len(distinct) == 1 else "Various Artists"
    artist = library_svc._get_or_create_artist(session, coll_artist_name)
    album = library_svc._get_or_create_album(session, name, artist.id, None)
    album.kind = "playlist"
    if album.owner_id is None:
        album.owner_id = user_id
    session.add(album)
    session.flush()
    _ensure_album_save(session, user_id, album.id)
    return album.id, artist.name


def _link_track_to_album(session, track_id: int, album_id: int, position: Optional[int]) -> bool:
    """Crea AlbumTrack si no existe. Devuelve True si añadió."""
    existing = session.exec(
        select(AlbumTrack).where(
            AlbumTrack.album_id == album_id,
            AlbumTrack.track_id == track_id,
        )
    ).first()
    if existing:
        return False
    session.add(AlbumTrack(album_id=album_id, track_id=track_id, position=position))
    return True


# ─── Dedup difuso (misma canción desde cualquier fuente) ──────

# Margen de duración para considerar dos pistas la MISMA. Generoso para tolerar
# el relleno de silencio típico entre fuentes (Spotify vs YouTube), pero corto
# frente a remixes/extendidos (que además suelen llevar otro título).
DEDUP_DURATION_TOL_MS = 10_000


def _norm_match(s: Optional[str]) -> str:
    """Normaliza para comparar (minúsculas, sin acentos, sin signos)."""
    return downloader._norm_text(s or "")


def _artist_matches(a: str, b: str) -> bool:
    """Artistas 'iguales' siendo tolerante con créditos/sufijos de canal."""
    if not a or not b:
        return False
    return a == b or a in b or b in a


def _build_track_index(session) -> dict[str, list[tuple[Track, str]]]:
    """Índice título_normalizado → [(Track, artista_normalizado)] para dedup."""
    rows = session.exec(
        select(Track, Artist.name).join(Artist, Artist.id == Track.artist_id)
    ).all()
    idx: dict[str, list[tuple[Track, str]]] = {}
    for track, artist_name in rows:
        idx.setdefault(_norm_match(track.title), []).append((track, _norm_match(artist_name)))
    return idx


def _is_same_track(meta: spotify.TrackMeta, track: Track, track_artist_norm: str) -> bool:
    """Confirma que un candidato (mismo título normalizado) es la misma canción:
    artista solapado y duración dentro de tolerancia. Conservador a propósito."""
    if not _artist_matches(_norm_match(meta.primary_artist), track_artist_norm):
        return False
    md, td = meta.duration_ms or 0, track.duration_ms or 0
    if md and td and abs(md - td) > DEDUP_DURATION_TOL_MS:
        return False
    return True


def _find_existing_track(
    session, meta: spotify.TrackMeta, index: dict[str, list[tuple[Track, str]]]
) -> Optional[Track]:
    """¿Ya está esta canción en la biblioteca? Mira (1) el id externo exacto y,
    si no, (2) título normalizado + artista + duración, para cazar la MISMA
    canción venga de Spotify, YouTube, SoundCloud o subida local."""
    if meta.spotify_id:
        t = session.exec(select(Track).where(Track.external_id == meta.spotify_id)).first()
        if t:
            return t
    for track, artist_norm in index.get(_norm_match(meta.title), []):
        if _is_same_track(meta, track, artist_norm):
            return track
    return None


def create_jobs_from_url(
    url: str,
    overrides: Optional[IngestOverrides] = None,
    user_id: Optional[int] = None,
    only_ids: Optional[list[str]] = None,
) -> dict:
    """Resuelve la URL y crea Jobs en BD, con dedup: si la pista ya existe
    en la biblioteca, simplemente la añade al álbum destino del user.

    Si `only_ids` viene, solo se procesan las pistas cuyo spotify_id esté ahí
    (deselección de pistas de una playlist desde la UI)."""
    result, source = _resolve_any(url)
    if only_ids:
        wanted = set(only_ids)
        result.tracks = [t for t in result.tracks if t.spotify_id in wanted]
    created: list[int] = []
    deduped: list[dict] = []
    skipped: list[str] = []

    with session_scope() as session:
        # Una PLAYLIST (YT o Spotify) se agrupa en UNA colección multi-artista,
        # no en un álbum por artista. Forzamos álbum=nombre de la playlist y
        # album_artist=Various Artists (o el único artista si todas coinciden),
        # conservando el artista real de cada pista. Solo si el user no pidió un
        # álbum destino explícito.
        playlist_album_id: Optional[int] = None
        no_explicit_target = not (overrides and (overrides.target_album_id or overrides.album))
        if result.kind == "playlist" and user_id and result.tracks and no_explicit_target:
            playlist_album_id, coll_artist = _collection_album_for_playlist(
                session, result.name, result.tracks, user_id
            )
            for m in result.tracks:
                m.album = result.name
                m.album_artist = coll_artist
        elif result.kind == "track" and no_explicit_target:
            # Canción individual = SUELTA por defecto (sin álbum). Solo se agrupa
            # si el user eligió crear un álbum o añadir a uno existente (overrides).
            for m in result.tracks:
                m.album = ""

        track_index = _build_track_index(session)
        batch_seen: list[tuple[str, str, int]] = []  # (titulo_n, artista_n, dur) ya encolados

        for meta in result.tracks:
            # Un override de artista en una playlist nombra a la colección; no
            # puede convertir todas sus canciones al mismo artista. El artista
            # por pista resuelto por Spotify/YouTube se conserva siempre.
            _apply_overrides(
                meta,
                overrides,
                apply_track_artist=result.kind != "playlist",
            )

            # Dedup contra la biblioteca: id externo exacto y, si no, parecido
            # (título+artista+duración) para cazar la MISMA canción desde Spotify,
            # YouTube, SoundCloud o subida local aunque el id externo sea distinto.
            existing_track = _find_existing_track(session, meta, track_index)
            if existing_track:
                # Casada por parecido y sin id externo: se lo asignamos para que la
                # próxima vez case por id exacto (y no overwritear si ya tenía uno).
                if not existing_track.external_id and meta.spotify_id:
                    existing_track.external_id = meta.spotify_id
                    session.add(existing_track)
                target = playlist_album_id or _resolve_target_album(
                    session, overrides, user_id, meta, result.kind
                )
                added_to = None
                if target:
                    if _link_track_to_album(session, existing_track.id, target, meta.track_number):
                        added_to = target
                deduped.append({
                    "spotify_id": meta.spotify_id,
                    "title": meta.title,
                    "track_id": existing_track.id,
                    "added_to_album_id": added_to,
                })
                continue

            # Dedup DENTRO de esta misma importación (la misma canción repetida en
            # la playlist, o desde dos vídeos de YouTube distintos).
            tn, an, dm = _norm_match(meta.title), _norm_match(meta.primary_artist), meta.duration_ms or 0
            if any(
                tn == bt and _artist_matches(an, ba)
                and not (dm and bd and abs(dm - bd) > DEDUP_DURATION_TOL_MS)
                for bt, ba, bd in batch_seen
            ):
                skipped.append(meta.spotify_id)
                continue

            # ¿Ya hay un job idéntico pendiente o en curso?
            existing = session.exec(
                select(Job).where(Job.spotify_track_id == meta.spotify_id)
            ).first()
            if existing and existing.status in ("pending", "running"):
                skipped.append(meta.spotify_id)
                continue
            # Si el job antiguo era 'done' o 'failed' lo borramos para no chocar con el unique
            if existing:
                session.delete(existing)
                session.flush()

            # Determinar target album para que el worker lo enganche al terminar
            target_for_job = playlist_album_id or _resolve_target_album(
                session, overrides, user_id, meta, result.kind
            )

            job = Job(
                # source_url debe ser el de la PISTA individual (el resolver lo
                # construye como watch?v=<id>), nunca el de la playlist: si no,
                # la descarga directa baja la playlist entera y un solo vídeo
                # caído tumba todas las pistas.
                source_url=meta.source_url or url,
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
                user_id=user_id,
                target_album_id=target_for_job,
                status="pending",
            )
            session.add(job)
            session.flush()
            created.append(job.id)
            batch_seen.append((tn, an, dm))

    wake()
    return {
        "source": source,
        "kind": result.kind,
        "name": result.name,
        "total_tracks": len(result.tracks),
        "created_job_ids": created,
        "deduped": deduped,
        "skipped_track_ids": skipped,
    }


# ─── Pipeline de un job ────────────────────────────────────────


def _load_meta_from_job(job: Job) -> spotify.TrackMeta:
    """Reconstruye TrackMeta desde el Job (info ya capturada al crearlo)."""
    artists = [a.strip() for a in (job.artists_csv or job.artist or "").split(",") if a.strip()]
    # source_kind del Job es 'track'|'album'|'playlist'; el provider real está en
    # el prefijo del ID o se infiere de la URL.
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


def _update_job_progress(job_id: int, pct: int, stage: str) -> None:
    """Helper para el progress_hook. Escribe directo a BD."""
    try:
        with session_scope() as s:
            job = s.get(Job, job_id)
            if not job or job.status != "running":
                return
            job.progress = pct
            job.stage = stage
            s.add(job)
    except Exception:
        pass


def process_job(job_id: int) -> None:
    """Ejecuta el pipeline completo para un job. Síncrono (bloqueante)."""
    with session_scope() as s:
        job = s.get(Job, job_id)
        if not job:
            return
        job.status = "running"
        job.started_at = datetime.utcnow()
        job.progress = 0
        job.stage = "iniciando"
        job.error = None
        s.add(job)

    try:
        meta = _load_meta_for_job_safe(job_id)
        if meta is None:
            return

        _update_job_progress(job_id, 5, "preparando")

        def progress_cb(pct: int, stage: str) -> None:
            _update_job_progress(job_id, pct, stage)

        dl_result = downloader.download(meta, progress_cb=progress_cb)
        if not dl_result.success:
            _mark_failed(job_id, dl_result.backend, dl_result.error or "download failed")
            return

        # Las playlists de Spotify resuelven SIN portada por pista (el item no la
        # trae). Si es una pista de Spotify (id sin prefijo yt:/sc:), pedimos su
        # portada real por id antes de caer a la miniatura de YouTube.
        if not meta.cover_url and meta.spotify_id and not meta.spotify_id.startswith(("yt:", "sc:")):
            try:
                meta.cover_url = spotify.fetch_track_meta(meta.spotify_id).cover_url
            except Exception:
                pass

        # Si aún no hay carátula, usar la miniatura del vídeo de YouTube del que
        # se descargó.
        if not meta.cover_url and dl_result.source_url:
            vid = _yt_video_id(dl_result.source_url)
            if vid:
                meta.cover_url = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"

        # Organize (tags + cover)
        _update_job_progress(job_id, 97, "etiquetando")
        try:
            final_path = organizer.organize(dl_result.file_path, meta)
        except Exception as e:
            log.exception("organize falló")
            _mark_failed(job_id, dl_result.backend, f"organize: {e}")
            return

        # Index en BD
        _update_job_progress(job_id, 99, "indexando")
        track_id = scanner.index_file(final_path)
        if track_id is None:
            # Se descargó pero no se pudo indexar: marcar fallido en vez de
            # 'done' fantasma (descarga completa pero la pista no sale en la app).
            _mark_failed(job_id, dl_result.backend, f"indexado falló: {final_path.name}")
            return

        with session_scope() as s:
            job = s.get(Job, job_id)
            if job:
                job.status = "done"
                job.progress = 100
                job.stage = None
                job.backend_used = dl_result.backend
                job.result_track_id = track_id
                job.completed_at = datetime.utcnow()
                s.add(job)
            # Setear external_id + source_url + AlbumTrack para el álbum original
            if job and track_id:
                t = s.get(Track, track_id)
                if t:
                    t.external_id = job.spotify_track_id
                    if dl_result.source_url:
                        t.source_url = dl_result.source_url
                    s.add(t)
                    if t.album_id:
                        _link_track_to_album(s, t.id, t.album_id, t.track_number)
                        a = s.get(Album, t.album_id)
                        if a and a.owner_id is None and job.user_id:
                            a.owner_id = job.user_id
                            s.add(a)
                        # El álbum/playlist importado aparece en tu biblioteca.
                        _ensure_album_save(s, job.user_id, t.album_id)
                    # Y enlazar al álbum destino si el user pidió uno custom
                    if job.target_album_id and job.target_album_id != t.album_id:
                        _link_track_to_album(s, t.id, job.target_album_id, t.track_number)
                        _ensure_album_save(s, job.user_id, job.target_album_id)
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


def retry_all_failed(user_id: Optional[int] = None) -> int:
    """Reencola todos los jobs en estado failed (opcionalmente de un user)."""
    n = 0
    with session_scope() as s:
        stmt = select(Job).where(Job.status == "failed")
        if user_id is not None:
            stmt = stmt.where(Job.user_id == user_id)
        for j in s.exec(stmt).all():
            j.status = "pending"
            j.error = None
            j.started_at = None
            j.completed_at = None
            s.add(j)
            n += 1
    if n:
        wake()
    return n


def clear_jobs(status: Optional[str] = None, user_id: Optional[int] = None) -> int:
    """Borra jobs por estado (o todos si status=None). Nunca borra running."""
    n = 0
    with session_scope() as s:
        stmt = select(Job)
        if status:
            stmt = stmt.where(Job.status == status)
        if user_id is not None:
            stmt = stmt.where(Job.user_id == user_id)
        for j in s.exec(stmt).all():
            if j.status == "running":
                continue
            s.delete(j)
            n += 1
    return n


def job_stats(user_id: Optional[int] = None) -> dict:
    """Resumen de la cola por estado, opcionalmente filtrado por user."""
    out = {"pending": 0, "running": 0, "done": 0, "failed": 0, "total": 0}
    with session_scope() as s:
        stmt = select(Job)
        if user_id is not None:
            stmt = stmt.where(Job.user_id == user_id)
        for j in s.exec(stmt).all():
            out["total"] += 1
            if j.status in out:
                out[j.status] += 1
    return out


def user_owns_job(job_id: int, user) -> bool:
    """True si el user puede mutar este job (es suyo o es admin)."""
    if user.is_admin:
        return True
    with session_scope() as s:
        j = s.get(Job, job_id)
        if not j:
            return False
        return j.user_id == user.id


# ─── Worker loop ───────────────────────────────────────────────


def _recover_stale_running_jobs() -> int:
    """Tras un reinicio, no hay worker procesando 'running' — los reencolamos."""
    n = 0
    with session_scope() as s:
        rows = s.exec(select(Job).where(Job.status == "running")).all()
        for j in rows:
            j.status = "pending"
            j.started_at = None
            j.error = "reanudado tras reinicio"
            s.add(j)
            n += 1
    if n:
        log.info("recuperados %d jobs running zombi", n)
    return n


async def _worker_loop() -> None:
    log.info("worker arrancado")
    _recover_stale_running_jobs()
    ev = _get_wake_event()
    while True:
        try:
            # Coger el siguiente pendiente. Toda la iteración está protegida:
            # antes, un fallo transitorio de SQLite aquí mataba el Task del
            # worker pero dejaba FastAPI vivo y la cola bloqueada para siempre.
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
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("worker: error en el bucle; reintentando en 5s")
            await asyncio.sleep(5)


def _worker_done(task: asyncio.Task) -> None:
    """Supervisa el Task: si termina inesperadamente, lo recrea."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        log.error("worker terminó inesperadamente; reiniciando", exc_info=exc)
    else:
        log.error("worker terminó inesperadamente sin excepción; reiniciando")
    try:
        asyncio.get_running_loop().call_later(1, start_worker)
    except RuntimeError:
        pass


def start_worker() -> None:
    global _worker_task
    if _worker_task is not None and not _worker_task.done():
        return
    loop = asyncio.get_event_loop()
    _worker_task = loop.create_task(_worker_loop())
    _worker_task.add_done_callback(_worker_done)


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
        "progress": j.progress,
        "stage": j.stage,
        "backend_used": j.backend_used,
        "error": j.error,
        "result_track_id": j.result_track_id,
        "user_id": j.user_id,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "completed_at": j.completed_at.isoformat() if j.completed_at else None,
    }
