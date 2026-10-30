"""Búsqueda web como evidencia para la IA. Pluggable y nunca fatal.

BBEAT_SEARCH_PROVIDER = searxng | none (por defecto none). Para añadir otro
proveedor (Brave, DuckDuckGo...) basta una función `(query, n) -> list[Snippet]`
registrada en PROVIDERS y su comprobación en `is_configured`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

import httpx

from app.config import settings

log = logging.getLogger("bbeat.ai.search")

TIMEOUT_S = 8.0
MAX_CONTENT = 300


@dataclass
class Snippet:
    title: str
    content: str
    url: str


def _searxng(query: str, n: int, client: Optional[httpx.Client] = None) -> list[Snippet]:
    base = settings.searxng_url.strip().rstrip("/")
    if not base:
        return []
    c = client or httpx
    r = c.get(
        f"{base}/search",
        params={"q": query, "format": "json"},
        headers={"User-Agent": "Bbeat/0.1"},
        timeout=TIMEOUT_S,
    )
    r.raise_for_status()
    out: list[Snippet] = []
    for it in (r.json().get("results") or [])[:n]:
        out.append(Snippet(
            title=str(it.get("title") or "")[:120],
            content=str(it.get("content") or "")[:MAX_CONTENT],
            url=str(it.get("url") or ""),
        ))
    return out


PROVIDERS: dict[str, Callable[[str, int], list[Snippet]]] = {"searxng": _searxng}


def provider() -> str:
    p = (settings.search_provider or "none").strip().lower()
    return p if p in PROVIDERS else "none"


def is_configured() -> bool:
    return provider() == "searxng" and bool(settings.searxng_url.strip())


def search(query: str, n: int = 5) -> list[Snippet]:
    """Top-N resultados; lista vacía si no está configurado o falla."""
    if not is_configured():
        return []
    try:
        return PROVIDERS[provider()](query, n)
    except Exception as e:  # nunca fatal: la IA sigue sin evidencia web
        log.warning("búsqueda web falló (%s): %s", query, e)
        return []
