"""Arnés de clasificación de géneros con IA, por ARTISTA.

Flujo: contexto del artista (pistas, géneros actuales, evidencia web) -> LLM ->
JSON validado contra el vocabulario CERRADO de géneros -> si la confianza llega
al mínimo se aplica; si no, va a la cola de revisión (GenreSuggestion).

Nunca se confía a ciegas: slugs inválidos se descartan, las excepciones por
pista exigen evidencia, y las pistas bloqueadas (genre_locked) no se tocan jamás.
Las pasadas son reanudables: un artista con filas en genre_suggestions ya está
clasificado y se salta salvo force.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

from sqlalchemy import case, delete, func
from sqlmodel import Session, select

from app.config import settings
from app.db import engine
from app.models import Album, Artist, GenreSuggestion, Track
from app.services import genre_store
from app.services.genres import GENRE_LABELS
from app.services.ai import search as search_svc
from app.services.ai.llm import (
    InvalidResponse, LLMClient, LLMConfig, LLMError, LLMNotConfigured, QuotaExceeded,
)

log = logging.getLogger("bbeat.ai.genres")

UNKNOWN = "unknown"
MAX_TRACKS_IN_PROMPT = 150
SMALL_ARTIST_TRACKS = 10  # hasta aquí un artista puede compartir petición
SKIP_ARTISTS = {"unknown artist", "various artists", "unknownartist", "variousartists", "va", ""}

# Descripción corta de cada género canónico, para que el modelo no adivine.
GENRE_DESCRIPTIONS = {
    "rap": "rap, hip-hop, trap, drill, boom bap",
    "reggaeton": "reggaetón, perreo, dembow, música urbana latina de club",
    "rock": "rock, punk, grunge, indie rock, rock alternativo, rock en español",
    "electronica": "electrónica, house, techno, EDM, dubstep, DnB, trance",
    "pop": "pop mainstream, dance-pop, synth-pop, pop latino de radio",
    "latino": "música latina: salsa, bachata, cumbia, regional mexicano, balada, tropical",
    "rnb": "R&B, soul, funk, neo-soul",
    "reggae": "reggae, dancehall, ska, dub",
    "metal": "heavy metal, thrash, death, black, power metal, metalcore",
    "jazz": "jazz, bebop, swing, fusión",
    "blues": "blues, blues rock",
    "folk": "folk, country, singer-songwriter acústico, americana",
    "clasica": "música clásica, ópera, orquestal, instrumental académico",
    "bso": "bandas sonoras y música de películas, series o videojuegos",
    "mundo": "músicas del mundo: africana, asiática, celta, flamenco, etc.",
    "infantil": "música infantil, nanas, canciones para niños",
    "podcast": "podcasts, programas hablados, entrevistas, charlas (no música)",
}

SYSTEM_PROMPT = """Eres un experto en música que clasifica artistas en un género de una lista CERRADA.

Reglas:
- Elige el género PRINCIPAL del artista (el que mejor lo define en toda su obra) usando SOLO un slug de la lista dada.
- Usa la evidencia aportada (pistas, géneros actuales de la biblioteca, resultados web) y tu conocimiento. Los géneros actuales de la biblioteca pueden estar mal: no los des por buenos.
- Lista "exceptions" SOLO para pistas concretas que claramente pertenezcan a otro género de la lista (p. ej. un tema acústico de un artista de rock no es excepción; una colaboración puramente rap de un artista pop sí). Sin evidencia clara, no pongas excepciones.
- Si no estás seguro o no conoces al artista, responde "unknown" como artist_genre. Nunca inventes.
- confidence es un número entre 0 y 1 (0.9+ solo si estás seguro).
- reason: una frase corta en español.
- Responde ÚNICAMENTE con un objeto JSON, sin texto adicional ni vallas de código.

Formato (un elemento por cada artista pedido):
{"results":[{"artist_id":<int>,"artist_genre":"<slug|unknown>","confidence":<0-1>,"reason":"<frase>","exceptions":[{"track_id":<int>,"genre":"<slug>","reason":"<frase>"}]}]}"""


# ─── Datos ───────────────────────────────────────────────────────


@dataclass
class TrackInfo:
    id: int
    title: str
    album: Optional[str]
    genre: Optional[str]
    locked: bool = False


@dataclass
class ArtistCtx:
    id: int
    name: str
    tracks: list[TrackInfo]
    snippets: list[search_svc.Snippet] = field(default_factory=list)

    @property
    def dist(self) -> Counter:
        c: Counter = Counter()
        for t in self.tracks:
            g = (t.genre or "").strip().lower()
            c[g or "(sin género)"] += 1
        return c


@dataclass
class Exc:
    track_id: int
    genre: str
    reason: str = ""


@dataclass
class Verdict:
    artist_id: int
    genre: Optional[str]  # slug canónico o None si 'unknown'
    confidence: float
    reason: str = ""
    exceptions: list[Exc] = field(default_factory=list)


@dataclass
class Outcome:
    ctx: ArtistCtx
    verdict: Verdict
    status: str  # applied | pending | skipped
    changes: dict[int, str] = field(default_factory=dict)  # track_id -> género nuevo


@dataclass
class RunResult:
    outcomes: list[Outcome] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    requests: int = 0
    quota_exceeded: bool = False
    retry_after: Optional[float] = None
    remaining: int = 0  # artistas candidatos que no se llegaron a procesar

    def count(self, status: str) -> int:
        return sum(1 for o in self.outcomes if o.status == status)


# ─── Configuración / estado ──────────────────────────────────────


def is_enabled() -> bool:
    return LLMConfig.from_settings().enabled


def config_summary() -> dict:
    """Estado de la configuración sin secretos, para la UI de admin."""
    c = LLMConfig.from_settings()
    return {
        "enabled": c.enabled,
        "provider": c.provider,
        "model": c.model if c.provider != "none" else "",
        "base_url_custom": bool(settings.ai_base_url.strip()),
        "api_key_set": bool(c.api_key),
        "rpm": c.rpm,
        "min_confidence": settings.ai_min_confidence,
        "search_provider": search_svc.provider(),
        "search_configured": search_svc.is_configured(),
        "artist_consistency": settings.artist_consistency,
    }


# ─── Prompt y validación ─────────────────────────────────────────


def _slug_from(value: Any) -> Optional[str]:
    """Slug canónico (o UNKNOWN) a partir de lo que devuelva el modelo."""
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    if v in GENRE_LABELS:
        return v
    if v in ("unknown", "desconocido", "unsure", "n/a", "none", ""):
        return UNKNOWN
    for slug, label in GENRE_LABELS.items():
        if v == label.lower():
            return slug
    return None


def build_prompt(ctxs: list[ArtistCtx]) -> str:
    lines = ["Géneros permitidos (slug: nombre — qué incluye):"]
    for slug, label in GENRE_LABELS.items():
        lines.append(f"- {slug}: {label} — {GENRE_DESCRIPTIONS.get(slug, '')}")
    lines.append("")
    for c in ctxs:
        lines.append(f'=== ARTISTA artist_id={c.id} nombre="{c.name}" ===')
        dist = ", ".join(f"{g}: {n}" for g, n in c.dist.most_common())
        lines.append(f"Géneros actuales en la biblioteca (pueden estar mal): {dist}")
        if c.snippets:
            lines.append("Evidencia web:")
            for s in c.snippets:
                lines.append(f"  * {s.title}: {s.content} ({s.url})")
        lines.append("Pistas (track_id | título | álbum | género actual):")
        for t in c.tracks[:MAX_TRACKS_IN_PROMPT]:
            lines.append(f"  {t.id} | {t.title} | {t.album or '-'} | {t.genre or '-'}")
        if len(c.tracks) > MAX_TRACKS_IN_PROMPT:
            lines.append(f"  (+{len(c.tracks) - MAX_TRACKS_IN_PROMPT} pistas más no listadas)")
        lines.append("")
    lines.append("Devuelve el JSON con un resultado por cada artist_id anterior.")
    return "\n".join(lines)


def parse_response(data: Any, ctxs: list[ArtistCtx]) -> dict[int, Verdict]:
    """Valida el JSON del modelo. Lanza ValueError si no hay nada utilizable."""
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        items = data["results"]
    elif isinstance(data, list):
        items = data
    elif isinstance(data, dict) and "artist_genre" in data:
        items = [data]
    else:
        raise ValueError("falta 'results'")
    by_id = {c.id: c for c in ctxs}
    out: dict[int, Verdict] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        aid = it.get("artist_id")
        if aid is None and len(ctxs) == 1:
            aid = ctxs[0].id
        try:
            aid = int(aid)
        except (TypeError, ValueError):
            continue
        ctx = by_id.get(aid)
        if ctx is None:
            continue
        genre = _slug_from(it.get("artist_genre"))
        if genre is None:
            raise ValueError(f"género fuera de la lista: {it.get('artist_genre')!r}")
        try:
            conf = float(it.get("confidence", 0))
        except (TypeError, ValueError):
            conf = 0.0
        conf = min(1.0, max(0.0, conf))
        valid_ids = {t.id for t in ctx.tracks}
        exceptions: list[Exc] = []
        seen: set[int] = set()
        for e in it.get("exceptions") or []:
            if not isinstance(e, dict):
                continue
            try:
                tid = int(e.get("track_id"))
            except (TypeError, ValueError):
                continue
            eg = _slug_from(e.get("genre"))
            if tid not in valid_ids or tid in seen or eg in (None, UNKNOWN) or eg == genre:
                continue
            seen.add(tid)
            exceptions.append(Exc(tid, eg, str(e.get("reason") or "")[:300]))
        out[aid] = Verdict(
            artist_id=aid,
            genre=None if genre == UNKNOWN else genre,
            confidence=conf,
            reason=str(it.get("reason") or "")[:300],
            exceptions=[] if genre == UNKNOWN else exceptions,
        )
    if not out:
        raise ValueError("ningún artista válido en la respuesta")
    return out


# ─── Contexto desde la BD ────────────────────────────────────────


def load_ctx(session: Session, artist: Artist) -> ArtistCtx:
    rows = session.exec(
        select(Track.id, Track.title, Album.title, Track.genre, Track.genre_locked)
        .outerjoin(Album, Album.id == Track.album_id)
        .where(Track.artist_id == artist.id)
        .order_by(Track.id)
    ).all()
    return ArtistCtx(
        id=artist.id,
        name=artist.name,
        tracks=[TrackInfo(i, t, a, g, bool(lk)) for i, t, a, g, lk in rows],
    )


def gather_snippets(name: str, search: Callable[[str, int], list]) -> list:
    seen: set[str] = set()
    out = []
    for q in (f"{name} género musical", f"{name} music genre"):
        for s in search(q, 4):
            if s.url not in seen:
                seen.add(s.url)
                out.append(s)
    return out[:6]


# ─── Candidatos ──────────────────────────────────────────────────


def candidate_artist_ids(
    session: Session,
    *,
    force: bool = False,
    only_missing: bool = False,
    suspicious: bool = False,
    names: Optional[list[str]] = None,
) -> list[int]:
    """Artistas a clasificar, los de más pistas primero."""
    empty = (Track.genre.is_(None)) | (func.trim(Track.genre) == "")
    rows = session.exec(
        select(
            Track.artist_id,
            func.count(Track.id),
            func.sum(case((empty, 1), else_=0)),
            func.sum(case((Track.genre_locked.is_(True), 1), else_=0)),
            func.count(func.distinct(func.lower(Track.genre))),
        ).group_by(Track.artist_id)
    ).all()
    done = set() if force else set(session.exec(select(GenreSuggestion.artist_id).distinct()).all())
    wanted = None
    if names:
        wanted = {re.sub(r"\s+", " ", n.strip().lower()) for n in names}
    artists = {a.id: a for a in session.exec(select(Artist)).all()}
    out: list[tuple[int, int]] = []
    for aid, n, missing, locked, ngen in rows:
        a = artists.get(aid)
        if a is None or aid in done or (a.name_normalized or "") in SKIP_ARTISTS:
            continue
        if wanted is not None and a.name_normalized not in wanted:
            continue
        if (locked or 0) >= n:  # todo bloqueado: nada que hacer
            continue
        missing = missing or 0
        if only_missing and not missing:
            continue
        if suspicious and not (missing or ngen > 1 or n <= 2):
            continue
        out.append((aid, n))
    out.sort(key=lambda x: -x[1])
    return [a for a, _ in out]


# ─── Planificación y persistencia ────────────────────────────────


def plan_changes(ctx: ArtistCtx, v: Verdict) -> dict[int, str]:
    """track_id -> género nuevo. Respeta bloqueos y aplica las excepciones."""
    if v.genre is None:
        return {}
    exc = {e.track_id: e.genre for e in v.exceptions}
    changes: dict[int, str] = {}
    for t in ctx.tracks:
        if t.locked:
            continue
        target = exc.get(t.id, v.genre)
        if (t.genre or "").strip().lower() != target:
            changes[t.id] = target
    return changes


def _dominant(ctx: ArtistCtx) -> Optional[str]:
    c = Counter((t.genre or "").strip().lower() for t in ctx.tracks if (t.genre or "").strip())
    return c.most_common(1)[0][0] if c else None


def store_outcome(
    session: Session,
    ctx: ArtistCtx,
    v: Verdict,
    *,
    min_confidence: float,
    apply: bool,
    write_tag: Optional[Callable[[str, str], Optional[str]]] = None,
) -> Outcome:
    """Decide aplicar/revisar/saltar; con apply=True lo persiste."""
    if v.genre is None:
        status = "skipped"
    elif v.confidence >= min_confidence:
        status = "applied"
    else:
        status = "pending"
    changes = plan_changes(ctx, v) if status == "applied" else {}
    out = Outcome(ctx, v, status, changes)
    if not apply:
        return out

    # Reclasificar sustituye lo anterior del artista (--force).
    session.exec(delete(GenreSuggestion).where(GenreSuggestion.artist_id == ctx.id))
    prev = _dominant(ctx)
    session.add(GenreSuggestion(
        artist_id=ctx.id, genre=v.genre, previous_genre=prev,
        confidence=v.confidence, reason=v.reason, status=status,
    ))
    for e in v.exceptions:
        track = next((t for t in ctx.tracks if t.id == e.track_id), None)
        session.add(GenreSuggestion(
            artist_id=ctx.id, track_id=e.track_id, genre=e.genre,
            previous_genre=track.genre if track else None,
            confidence=v.confidence, reason=e.reason, status=status,
        ))
    if status == "applied":
        done: dict[int, str] = {}
        for tid, g in changes.items():
            t = session.get(Track, tid)
            if t is not None and genre_store.set_track_genre(session, t, g, "ai", write_tag=write_tag):
                done[tid] = g
        out.changes = done
    session.commit()
    return out


def accept_suggestion(
    session: Session,
    suggestion_id: int,
    genre: Optional[str] = None,
    *,
    write_tag: Optional[Callable[[str, str], Optional[str]]] = None,
) -> int:
    """Acepta una sugerencia (opcionalmente con otro género). Devuelve pistas cambiadas.

    Con otro género distinto del sugerido es una decisión humana: se bloquea.
    Las pistas bloqueadas no se tocan nunca.
    """
    s = session.get(GenreSuggestion, suggestion_id)
    if s is None:
        raise LookupError("sugerencia no encontrada")
    if s.status != "pending":
        raise ValueError("la sugerencia ya está resuelta")
    final = _slug_from(genre) if genre else s.genre
    if final in (None, UNKNOWN):
        raise ValueError("género no válido")
    manual = bool(genre) and final != s.genre
    source = "manual" if manual else "ai"

    if s.track_id is not None:
        tracks = [session.get(Track, s.track_id)]
    else:
        # Artista: todas sus pistas salvo las que tienen excepción propia.
        exc_ids = set(session.exec(
            select(GenreSuggestion.track_id).where(
                GenreSuggestion.artist_id == s.artist_id, GenreSuggestion.track_id.is_not(None)
            )
        ).all())
        tracks = [t for t in session.exec(select(Track).where(Track.artist_id == s.artist_id)).all()
                  if t.id not in exc_ids]
    n = 0
    for t in tracks:
        if t is None or t.genre_locked:
            continue
        if genre_store.set_track_genre(session, t, final, source, lock=manual, write_tag=write_tag):
            n += 1
    s.genre = final
    s.status = "applied"
    session.add(s)
    session.commit()
    return n


def reject_suggestion(session: Session, suggestion_id: int) -> None:
    s = session.get(GenreSuggestion, suggestion_id)
    if s is None:
        raise LookupError("sugerencia no encontrada")
    s.status = "rejected"
    session.add(s)
    session.commit()


def set_artist_genre(
    session: Session,
    artist_id: int,
    genre: str,
    *,
    write_tag: Optional[Callable[[str, str], Optional[str]]] = None,
) -> dict:
    """Edición manual de artista: todas sus pistas, bloqueadas como 'manual'."""
    slug = _slug_from(genre)
    g = slug if slug and slug != UNKNOWN else genre.strip().lower()
    if not g:
        raise ValueError("género vacío")
    tracks = session.exec(select(Track).where(Track.artist_id == artist_id)).all()
    changed = failed = 0
    for t in tracks:
        if genre_store.set_track_genre(session, t, g, "manual", lock=True, write_tag=write_tag):
            changed += 1
        else:
            failed += 1
    # Lo que la IA tuviera pendiente de este artista queda superado.
    for s in session.exec(select(GenreSuggestion).where(
        GenreSuggestion.artist_id == artist_id, GenreSuggestion.status == "pending"
    )).all():
        s.status = "rejected"
        session.add(s)
    session.commit()
    return {"genre": g, "tracks": len(tracks), "changed": changed, "failed": failed}


# ─── Ejecución ───────────────────────────────────────────────────


def _batches(ids: list[int], sizes: dict[int, int], max_artists: int) -> list[list[int]]:
    """Agrupa artistas pequeños; los grandes van solos."""
    out: list[list[int]] = []
    cur: list[int] = []
    for aid in ids:
        if sizes[aid] > SMALL_ARTIST_TRACKS:
            out.append([aid])
            continue
        cur.append(aid)
        if len(cur) >= max(1, max_artists):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def run(
    *,
    apply: bool = False,
    limit: int = 0,
    force: bool = False,
    only_missing: bool = False,
    suspicious: bool = False,
    names: Optional[list[str]] = None,
    llm: Optional[LLMClient] = None,
    search: Optional[Callable[[str, int], list]] = None,
    min_confidence: Optional[float] = None,
    write_tag: Optional[Callable[[str, str], Optional[str]]] = None,
    on_outcome: Optional[Callable[[Outcome], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    on_start: Optional[Callable[[int], None]] = None,
) -> RunResult:
    """Clasifica artistas. Para limpiamente ante QuotaExceeded (reanudable)."""
    own_llm = llm is None
    llm = llm or LLMClient()
    if not llm.cfg.enabled:
        raise LLMNotConfigured("IA no configurada")
    search = search or search_svc.search
    minc = settings.ai_min_confidence if min_confidence is None else min_confidence
    res = RunResult()
    try:
        with Session(engine) as session:
            ids = candidate_artist_ids(
                session, force=force, only_missing=only_missing, suspicious=suspicious, names=names
            )
            if limit:
                ids = ids[:limit]
            sizes = dict(session.exec(
                select(Track.artist_id, func.count(Track.id)).group_by(Track.artist_id)
            ).all())
        res.remaining = len(ids)
        if on_start:
            on_start(len(ids))
        failures = 0
        for batch in _batches(ids, sizes, settings.ai_batch_artists):
            if should_stop and should_stop():
                break
            with Session(engine) as session:
                ctxs = [load_ctx(session, session.get(Artist, a)) for a in batch]
                for c in ctxs:
                    c.snippets = gather_snippets(c.name, search)
                try:
                    verdicts = llm.chat_json(
                        SYSTEM_PROMPT, build_prompt(ctxs), lambda d: parse_response(d, ctxs)
                    )
                except QuotaExceeded as e:
                    res.quota_exceeded = True
                    res.retry_after = e.retry_after
                    break
                except InvalidResponse as e:
                    res.errors.append(f"respuesta inválida para {[c.name for c in ctxs]}: {e}")
                    res.remaining -= len(batch)
                    continue
                except LLMNotConfigured:
                    raise
                except LLMError as e:
                    res.errors.append(str(e))
                    failures += 1
                    if failures >= 3:  # algo va mal de forma sostenida: no seguir quemando cuota
                        break
                    continue
                failures = 0
                for c in ctxs:
                    v = verdicts.get(c.id)
                    if v is None:
                        res.errors.append(f"el modelo no devolvió {c.name}")
                        continue
                    o = store_outcome(session, c, v, min_confidence=minc, apply=apply, write_tag=write_tag)
                    res.outcomes.append(o)
                    if on_outcome:
                        on_outcome(o)
                res.remaining -= len(batch)
    finally:
        res.requests = llm.requests
        if own_llm:
            llm.close()
    return res


# ─── Estado para la UI y ejecución en segundo plano ──────────────


@dataclass
class RunState:
    running: bool = False
    total: int = 0
    done: int = 0
    applied: int = 0
    pending: int = 0
    skipped: int = 0
    errors: int = 0
    quota_exceeded: bool = False
    message: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def as_dict(self) -> dict:
        return dict(self.__dict__)


state = RunState()
_run_lock = threading.Lock()
_stop = threading.Event()


def request_stop() -> None:
    _stop.set()


def start_background(*, limit: int = 25, only_missing: bool = False, force: bool = False,
                     **run_kwargs) -> bool:
    """Lanza una pasada en un hilo. False si ya hay una en marcha."""
    if not _run_lock.acquire(blocking=False):
        return False
    _stop.clear()
    global state
    state = RunState(running=True, total=limit or 0, started_at=datetime.utcnow().isoformat())

    def _work():
        try:
            def _on(o: Outcome):
                state.done += 1
                setattr(state, o.status, getattr(state, o.status) + 1)
                state.message = o.ctx.name

            res = run(apply=True, limit=limit, only_missing=only_missing, force=force,
                      on_outcome=_on, should_stop=_stop.is_set,
                      on_start=lambda n: setattr(state, "total", n), **run_kwargs)
            state.errors = len(res.errors)
            state.quota_exceeded = res.quota_exceeded
            if res.quota_exceeded:
                state.message = "Cuota del proveedor agotada: vuelve a lanzarlo más tarde, continúa donde lo dejó."
            elif res.errors:
                state.message = res.errors[-1]
            else:
                state.message = "Terminado."
        except Exception as e:
            log.exception("clasificación con IA falló")
            state.errors += 1
            state.message = str(e)
        finally:
            state.running = False
            state.finished_at = datetime.utcnow().isoformat()
            _run_lock.release()

    threading.Thread(target=_work, name="ai-genres", daemon=True).start()
    return True


# Cola de importación: artistas con género desconocido o discutido.
DEBOUNCE_S = 45.0
_queue: set[str] = set()
_queue_lock = threading.Lock()
_queue_thread: Optional[threading.Thread] = None


def enqueue_artist(name: str) -> None:
    """Encola un artista tras una importación. No bloquea; no hace nada sin IA."""
    global _queue_thread
    if not name or not is_enabled():
        return
    with _queue_lock:
        _queue.add(name)
        if _queue_thread is not None and _queue_thread.is_alive():
            return
        _queue_thread = threading.Thread(target=_drain_queue, name="ai-genres-queue", daemon=True)
        _queue_thread.start()


def _drain_queue() -> None:
    time.sleep(DEBOUNCE_S)  # deja que terminen de indexarse las pistas del lote
    while True:
        with _queue_lock:
            names = sorted(_queue)
            _queue.clear()
        if not names:
            return
        if not _run_lock.acquire(timeout=600):
            return
        try:
            run(apply=True, names=names)
        except Exception:
            log.exception("clasificación de importación falló")
        finally:
            _run_lock.release()
