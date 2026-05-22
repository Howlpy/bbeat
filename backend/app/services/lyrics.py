"""Integración con LRCLIB para letras (gratis, sin auth).

Estrategia en dos pasos:
1. `/api/get` con duración → match exacto (LRCLIB exige ±2s de duración).
2. Si falla, `/api/search` por título+artista y se elige la candidata con
   letra cuya duración esté más cerca de la nuestra (prefiriendo synced). Así
   recuperamos letras que existen pero cuya duración difiere unos segundos.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

log = logging.getLogger("bbeat.lyrics")

LRCLIB_GET = "https://lrclib.net/api/get"
LRCLIB_SEARCH = "https://lrclib.net/api/search"
HEADERS = {"User-Agent": "Bbeat/0.1 (https://github.com/Howlpy/bbeat)"}


def _format(data: dict, approx: bool = False) -> Optional[dict]:
    """Convierte una respuesta de LRCLIB en nuestro dict, o None si no hay letra."""
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
    }


def _try_get(
    client: httpx.Client, artist: str, title: str, album: Optional[str], duration: Optional[int]
) -> Optional[dict]:
    """Match exacto por duración. None si 404 o sin letra."""
    params = {"artist_name": artist, "track_name": title}
    if album:
        params["album_name"] = album
    if duration and duration > 0:
        params["duration"] = duration
    r = client.get(LRCLIB_GET, params=params)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return _format(r.json())


def _try_search(
    client: httpx.Client, artist: str, title: str, duration: Optional[int]
) -> Optional[dict]:
    """Búsqueda laxa: elige la candidata con letra de duración más parecida."""
    r = client.get(LRCLIB_SEARCH, params={"track_name": title, "artist_name": artist})
    r.raise_for_status()
    results = r.json()
    if not isinstance(results, list):
        return None
    # Solo candidatas con letra real (ni instrumentales ni vacías).
    cands = [
        d
        for d in results
        if (d.get("syncedLyrics") or d.get("plainLyrics")) and not d.get("instrumental")
    ]
    if not cands:
        return None
    # Ordena por cercanía de duración (si la tenemos) y, a igualdad, prefiere synced.
    cands.sort(
        key=lambda d: (
            abs((d.get("duration") or 0) - duration) if duration else 0,
            0 if d.get("syncedLyrics") else 1,
        )
    )
    return _format(cands[0], approx=True)


def fetch_lyrics(
    artist: str,
    title: str,
    album: Optional[str] = None,
    duration_seconds: Optional[int] = None,
) -> dict:
    """Devuelve {found, plain, synced, source, ...}."""
    not_found = {"found": False, "plain": None, "synced": None, "source": "lrclib"}
    try:
        with httpx.Client(timeout=10, headers=HEADERS) as c:
            exact = _try_get(c, artist, title, album, duration_seconds)
            if exact:
                return exact
            approx = _try_search(c, artist, title, duration_seconds)
            if approx:
                return approx
    except Exception as e:
        log.warning("LRCLIB error: %s", e)
        return {**not_found, "error": str(e)}
    return not_found
