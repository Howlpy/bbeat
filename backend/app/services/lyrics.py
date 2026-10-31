"""Letras desde LRCLIB (gratis, sin auth), con limpieza de metadatos, reintentos y caché.

Cadena de estrategias (se corta en el primer acierto):
1. /api/get (artista principal + título limpio [+ álbum si es un álbum real]).
2. /api/get con título/artista originales si difieren.
3. /api/search por campos, luego q="{artista} {título}", luego q="{título}".
Las candidatas de búsqueda se validan (artista/título/duración) y se ordenan.
Un fallo en un paso (tras reintentos) no aborta los siguientes.
"""
from __future__ import annotations

import logging
import re
import time
import unicodedata
from datetime import datetime, timedelta
from typing import Optional

import httpx

log = logging.getLogger("bbeat.lyrics")

LRCLIB_GET = "https://lrclib.net/api/get"
LRCLIB_SEARCH = "https://lrclib.net/api/search"
HEADERS = {"User-Agent": "Bbeat/0.1 (https://github.com/Howlpy/bbeat)"}

RETRY_STATUS = {429, 502, 503, 504}
BACKOFFS = (0.5, 1.5)
MAX_ATTEMPTS = 3
TOTAL_BUDGET = 12.0  # s para toda la búsqueda
DURATION_TOLERANCE = 15  # s
NEGATIVE_TTL = timedelta(days=3)

_sleep = time.sleep  # parcheable en tests


# ─── Normalización ───────────────────────────────────────────

_JUNK_SUFFIX = re.compile(
    r"^(?:\d{4}\b.*|.*\b(?:remaster(?:ed)?|live|remix|mix|version|versi[oó]n|"
    r"en directo|en vivo|directo|mono|stereo|radio edit|edit|acoustic|ac[uú]stico|"
    r"deluxe|bonus|sessions?|tiny desk|audio|video|visualizer|lyrics?)\b.*)$",
    re.IGNORECASE,
)
_FEAT_TAIL = re.compile(r"\s+(?:feat\.?|ft\.?|featuring)\s+.*$", re.IGNORECASE)
_ARTIST_SPLIT = re.compile(
    r"\s*(?:/|,|;|&|\+|\bfeat\.?(?=\s)|\bft\.?(?=\s)|\bfeaturing\b)\s*",
    re.IGNORECASE,
)


def _norm(s: Optional[str]) -> str:
    """Casefold, sin acentos ni puntuación, espacios colapsados."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s.casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]|_", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def clean_title(title: str) -> str:
    """Quita basura típica de YouTube/remasters: comillas, (…)/[…], feat., sufijos ' - …'."""
    t = (title or "").strip()
    out = re.sub(r"[“”„\"«»]", "", t)
    out = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", out)
    out = re.sub(r"\s+", " ", out).strip()
    out = _FEAT_TAIL.sub("", out)
    m = re.search(r"\s+[-–—]\s+(.*)$", out)
    if m and _JUNK_SUFFIX.match(m.group(1).strip()):
        out = out[: m.start()]
    out = re.sub(r"\s+", " ", out).strip(" -–—")
    return out or t


def artist_parts(artist: str) -> list[str]:
    """Partes del artista ('A / B', 'A & B', 'A feat. B') y el nombre completo; principal primero."""
    a = (artist or "").strip()
    parts = [p.strip() for p in _ARTIST_SPLIT.split(a) if p and p.strip()]
    out: list[str] = []
    for p in parts + ([a] if a else []):
        if p not in out:
            out.append(p)
    return out


def main_artist(artist: str) -> str:
    for p in _ARTIST_SPLIT.split((artist or "").strip()):
        if p and p.strip():
            return p.strip()
    return (artist or "").strip()


# ─── HTTP con reintentos ─────────────────────────────────────


class _Budget:
    def __init__(self, total: float = TOTAL_BUDGET):
        self.end = time.monotonic() + total

    def left(self) -> float:
        return self.end - time.monotonic()


def _request(client: httpx.Client, url: str, params: dict, budget: _Budget) -> httpx.Response:
    """GET con hasta 3 intentos (429/5xx/red). Devuelve 200 o 404; lanza si se agotan."""
    last: Exception = RuntimeError("sin intentos")
    for attempt in range(MAX_ATTEMPTS):
        if budget.left() <= 0.5:
            raise TimeoutError("presupuesto de tiempo agotado")
        delay = BACKOFFS[min(attempt, len(BACKOFFS) - 1)]
        try:
            r = client.get(url, params=params, timeout=min(8.0, budget.left()))
            if r.status_code in RETRY_STATUS:
                ra = r.headers.get("Retry-After", "")
                if ra.isdigit() and int(ra) <= 5:
                    delay = float(ra)
                last = httpx.HTTPStatusError(
                    f"HTTP {r.status_code}", request=r.request, response=r
                )
            elif r.status_code == 404:
                return r
            else:
                r.raise_for_status()  # otros 4xx/5xx: no se reintenta
                return r
        except httpx.HTTPStatusError as e:
            if e.response is None or e.response.status_code not in RETRY_STATUS:
                raise
        except httpx.HTTPError as e:
            last = e
        if attempt < MAX_ATTEMPTS - 1 and budget.left() > delay + 0.5:
            _sleep(delay)
        else:
            break
    raise last


# ─── Formato y validación ────────────────────────────────────


def _has_lyrics(d: dict) -> bool:
    return bool(d.get("plainLyrics") or d.get("syncedLyrics"))


def _format(data: dict, approx: bool = False) -> Optional[dict]:
    plain = data.get("plainLyrics") or None
    synced = data.get("syncedLyrics") or None
    if not plain and not synced:
        return None
    return {
        "found": True,
        "plain": plain,
        "synced": synced,
        "source": "lrclib (aprox)" if approx else "lrclib",
        "track_name": data.get("trackName"),
        "artist_name": data.get("artistName"),
        "approx": approx,
        "instrumental": False,
    }


def _artist_match(cand_artist: Optional[str], parts: list[str]) -> bool:
    ca = _norm(cand_artist)
    if not ca:
        return False
    for p in parts:
        pn = _norm(p)
        if pn and (pn in ca or ca in pn):
            return True
    return False


def pick_candidate(
    cands: list, parts: list[str], clean: str, duration: Optional[int]
) -> Optional[dict]:
    """Valida y ordena candidatas de búsqueda; devuelve la mejor o None."""
    tn = _norm(clean)
    scored = []
    for d in cands if isinstance(cands, list) else []:
        if not isinstance(d, dict) or not _has_lyrics(d) or d.get("instrumental"):
            continue
        a_ok = _artist_match(d.get("artistName"), parts)
        ct = _norm(d.get("trackName"))
        exact = bool(tn) and ct == tn
        contains = bool(tn) and bool(ct) and (tn in ct or ct in tn)
        cd = d.get("duration")
        known = bool(duration and duration > 0 and cd)
        diff = abs(cd - duration) if known else 0
        if known and diff > DURATION_TOLERANCE:
            continue
        if a_ok:
            if not (exact or contains):
                continue
        elif not (exact and known):
            # Sin artista coincidente solo vale título exacto con duración verificada.
            continue
        rank = (0 if a_ok else 1, 0 if exact else 1, diff, 0 if d.get("syncedLyrics") else 1)
        scored.append((rank, d))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0])
    return scored[0][1]


# ─── Búsqueda ────────────────────────────────────────────────


def _get(client, budget, artist, title, album, duration) -> Optional[dict]:
    params = {"artist_name": artist, "track_name": title}
    if album:
        params["album_name"] = album
    if duration and duration > 0:
        params["duration"] = duration
    r = _request(client, LRCLIB_GET, params, budget)
    if r.status_code == 404:
        return None
    data = r.json()
    return data if isinstance(data, dict) else None


def _search(client, budget, **params) -> list:
    r = _request(client, LRCLIB_SEARCH, params, budget)
    data = r.json() if r.status_code == 200 else []
    return data if isinstance(data, list) else []


def fetch_lyrics(
    artist: str,
    title: str,
    album: Optional[str] = None,
    duration_seconds: Optional[int] = None,
    transport: Optional[httpx.BaseTransport] = None,
) -> dict:
    """Devuelve {found, plain, synced, source, track_name, artist_name, approx,
    instrumental[, error]}. `album` solo debe pasarse si es un álbum real."""
    miss = {
        "found": False, "plain": None, "synced": None, "source": "lrclib",
        "track_name": None, "artist_name": None, "approx": False, "instrumental": False,
    }
    clean = clean_title(title)
    main = main_artist(artist)
    parts = artist_parts(artist)
    dur = duration_seconds if duration_seconds and duration_seconds > 0 else None
    budget = _Budget()
    errors: list[str] = []

    def step(fn, *a, **kw):
        """Ejecuta un paso; un fallo se anota y no aborta la cadena."""
        try:
            return fn(*a, **kw)
        except Exception as e:  # noqa: BLE001
            errors.append(str(e) or type(e).__name__)
            log.warning("LRCLIB paso falló: %s", e)
            return None

    with httpx.Client(timeout=10, headers=HEADERS, transport=transport) as c:
        # 1) get exacto (álbum solo si es real; si falla con álbum, sin él).
        exact = step(_get, c, budget, main, clean, album, dur)
        if exact is None and album:
            exact = step(_get, c, budget, main, clean, None, dur)
        # 2) get con valores originales si difieren.
        if exact is None and (title != clean or artist != main):
            exact = step(_get, c, budget, artist, title, None, dur)
        if exact:
            f = _format(exact)
            if f:
                return f
            if exact.get("instrumental"):
                return {**miss, "instrumental": True,
                        "track_name": exact.get("trackName"),
                        "artist_name": exact.get("artistName")}
        # 3) búsquedas.
        for params in (
            {"track_name": clean, "artist_name": main},
            {"q": f"{main} {clean}".strip()},
            {"q": clean},
        ):
            best = pick_candidate(step(_search, c, budget, **params) or [], parts, clean, dur)
            if best:
                f = _format(best, approx=True)
                if f:
                    return f
    if errors:
        return {**miss, "error": errors[-1]}
    return miss


# ─── Caché ───────────────────────────────────────────────────


def _row_to_dict(row) -> dict:
    return {
        "found": row.found, "plain": row.plain, "synced": row.synced,
        "source": row.source or "lrclib", "track_name": row.track_name,
        "artist_name": row.artist_name, "approx": row.approx,
        "instrumental": row.instrumental, "cached": True,
    }


def lookup(
    session,
    track_id: int,
    artist: str,
    title: str,
    album: Optional[str],
    duration_seconds: Optional[int],
    refresh: bool = False,
) -> dict:
    """Letra con caché: aciertos para siempre, negativos 3 días, errores nunca."""
    from app.models import LyricsCache

    row = session.get(LyricsCache, track_id)
    if row and not refresh:
        if row.found or datetime.utcnow() - row.fetched_at < NEGATIVE_TTL:
            return _row_to_dict(row)
    res = fetch_lyrics(artist, title, album, duration_seconds)
    if res.get("error"):
        return {**res, "cached": False}
    if row is None:
        row = LyricsCache(track_id=track_id)
    row.found = bool(res["found"])
    row.plain = res.get("plain")
    row.synced = res.get("synced")
    row.source = res.get("source")
    row.track_name = res.get("track_name")
    row.artist_name = res.get("artist_name")
    row.approx = bool(res.get("approx"))
    row.instrumental = bool(res.get("instrumental"))
    row.fetched_at = datetime.utcnow()
    session.add(row)
    session.commit()
    return {**res, "cached": False}


def invalidate(session, track_id: int) -> None:
    from app.models import LyricsCache

    row = session.get(LyricsCache, track_id)
    if row:
        session.delete(row)
        session.commit()
