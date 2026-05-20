"""Integración con LRCLIB para letras (gratis, sin auth)."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

log = logging.getLogger("bbeat.lyrics")

LRCLIB_API = "https://lrclib.net/api/get"


def fetch_lyrics(
    artist: str,
    title: str,
    album: Optional[str] = None,
    duration_seconds: Optional[int] = None,
) -> dict:
    """Devuelve {plain, synced, source, found}."""
    params = {"artist_name": artist, "track_name": title}
    if album:
        params["album_name"] = album
    if duration_seconds and duration_seconds > 0:
        params["duration"] = duration_seconds
    headers = {
        "User-Agent": "Bbeat/0.1 (https://github.com/Howlpy/bbeat)",
    }
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(LRCLIB_API, params=params, headers=headers)
        if r.status_code == 404:
            return {"found": False, "plain": None, "synced": None, "source": "lrclib"}
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("LRCLIB error: %s", e)
        return {
            "found": False,
            "plain": None,
            "synced": None,
            "source": "lrclib",
            "error": str(e),
        }

    return {
        "found": True,
        "plain": data.get("plainLyrics") or None,
        "synced": data.get("syncedLyrics") or None,
        "source": "lrclib",
        "track_name": data.get("trackName"),
        "artist_name": data.get("artistName"),
    }
