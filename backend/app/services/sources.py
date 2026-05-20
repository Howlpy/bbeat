"""Detección de la fuente de una URL para enrutar al resolver correcto."""
from __future__ import annotations

import re
from typing import Literal

SourceKind = Literal["spotify", "youtube", "soundcloud", "unknown"]

SPOTIFY_RE = re.compile(r"^(?:spotify:|https?://open\.spotify\.com/)", re.IGNORECASE)
YOUTUBE_RE = re.compile(
    r"^https?://(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)/", re.IGNORECASE
)
SOUNDCLOUD_RE = re.compile(
    r"^https?://(?:www\.|m\.|on\.)?soundcloud\.com/", re.IGNORECASE
)


def detect(url: str) -> SourceKind:
    u = (url or "").strip()
    if SPOTIFY_RE.match(u):
        return "spotify"
    if YOUTUBE_RE.match(u):
        return "youtube"
    if SOUNDCLOUD_RE.match(u):
        return "soundcloud"
    return "unknown"
