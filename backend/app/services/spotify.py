"""Resolución de URLs de Spotify usando SpotifyScraper (scraping de open.spotify.com).

No necesita Premium ni Developer App. Sortea el bloqueo de la Web API de
Spotify desde noviembre 2024.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from spotify_scraper import SpotifyClient

log = logging.getLogger("bbeat.spotify")

URL_PATTERN = re.compile(
    r"(?:spotify:|https?://open\.spotify\.com/(?:intl-\w+/)?)"
    r"(track|album|playlist)[/:]([a-zA-Z0-9]+)"
)
TRACK_URI_RE = re.compile(r"spotify:track:([a-zA-Z0-9]+)")


class IngestError(Exception):
    """Error de ingesta que debe mostrarse al usuario como 4xx."""


@dataclass
class TrackMeta:
    spotify_id: str
    title: str
    artists: list[str]
    album: str
    album_artist: str
    track_number: int
    disc_number: int
    total_tracks: int
    duration_ms: int
    isrc: Optional[str]
    year: Optional[int]
    cover_url: Optional[str]
    source_url: str = ""
    source_kind: str = "track"

    @property
    def primary_artist(self) -> str:
        return self.artists[0] if self.artists else "Unknown Artist"

    @property
    def search_query(self) -> str:
        return f"{self.primary_artist} - {self.title}"


@dataclass
class ResolveResult:
    kind: str
    name: str
    tracks: list[TrackMeta] = field(default_factory=list)


_client: Optional[SpotifyClient] = None


def get_client() -> SpotifyClient:
    global _client
    if _client is not None:
        return _client
    _client = SpotifyClient(timeout=30)
    return _client


def parse_url(url: str) -> tuple[str, str]:
    m = URL_PATTERN.search(url.strip())
    if not m:
        raise ValueError(f"URL de Spotify no reconocida: {url!r}")
    return m.group(1), m.group(2)


def normalize_url(url: str) -> str:
    """Devuelve la URL canónica que SpotifyScraper acepta.

    - Quita prefijos regionales `/intl-XX/`
    - Quita query params (`?si=...`)
    - Reconstruye desde el (kind, id) parseado
    """
    kind, spotify_id = parse_url(url)
    return f"https://open.spotify.com/{kind}/{spotify_id}"


def _pick_cover_url(images: list[dict], target: int = 640) -> Optional[str]:
    if not images:
        return None
    best = min(images, key=lambda i: abs((i.get("height") or 0) - target))
    return best.get("url")


def _track_id_from_uri(uri: str) -> str:
    m = TRACK_URI_RE.match(uri or "")
    return m.group(1) if m else ""


def _year_from_release_date(date: Optional[str]) -> Optional[int]:
    if not date:
        return None
    m = re.search(r"\d{4}", str(date))
    return int(m.group()) if m else None


def _track_from_album_item(item: dict, album: dict, album_artist: str, source_url: str) -> TrackMeta:
    cover = _pick_cover_url(album.get("images") or [])
    return TrackMeta(
        spotify_id=item.get("id") or _track_id_from_uri(item.get("uri", "")),
        title=item.get("name") or "Unknown Title",
        artists=[album_artist] if album_artist else [],
        album=album.get("name") or "",
        album_artist=album_artist,
        track_number=item.get("track_number") or 1,
        disc_number=item.get("disc_number") or 1,
        total_tracks=album.get("total_tracks") or len(album.get("tracks") or []),
        duration_ms=item.get("duration_ms") or 0,
        isrc=item.get("isrc"),
        year=_year_from_release_date(album.get("release_date")),
        cover_url=cover,
        source_url=source_url,
        source_kind="album",
    )


def _track_from_playlist_item(item: dict, source_url: str) -> TrackMeta:
    artists_raw = item.get("artists") or []
    # SpotifyScraper a veces mete varios artistas concatenados en una sola entrada
    flat = []
    for a in artists_raw:
        n = (a.get("name") or "").strip()
        if not n:
            continue
        # "PinkPantheress, Zara Larsson" → ["PinkPantheress", "Zara Larsson"]
        flat.extend([s.strip() for s in n.split(",") if s.strip()])
    return TrackMeta(
        spotify_id=item.get("id") or _track_id_from_uri(item.get("uri", "")),
        title=item.get("name") or "Unknown Title",
        artists=flat,
        album="",
        album_artist=flat[0] if flat else "",
        track_number=1,
        disc_number=1,
        total_tracks=1,
        duration_ms=item.get("duration_ms") or 0,
        isrc=None,
        year=None,
        cover_url=None,
        source_url=source_url,
        source_kind="playlist",
    )


def _track_meta_from_track_endpoint(
    track: dict, source_url: str, source_kind: str
) -> TrackMeta:
    """Para track URL: el album viene sin nombre (limitación de SpotifyScraper)."""
    artists = [a.get("name", "") for a in (track.get("artists") or []) if a.get("name")]
    album = track.get("album") or {}
    return TrackMeta(
        spotify_id=track.get("id") or "",
        title=track.get("name") or "Unknown Title",
        artists=artists,
        album=album.get("name") or "",
        album_artist=artists[0] if artists else "",
        track_number=1,
        disc_number=1,
        total_tracks=1,
        duration_ms=track.get("duration_ms") or 0,
        isrc=None,
        year=_year_from_release_date(track.get("release_date")),
        cover_url=_pick_cover_url(album.get("images") or []),
        source_url=source_url,
        source_kind=source_kind,
    )


def resolve_url(url: str) -> ResolveResult:
    kind, spotify_id = parse_url(url)
    clean_url = normalize_url(url)
    client = get_client()

    try:
        if kind == "track":
            track = client.get_track(clean_url).to_dict()
            meta = _track_meta_from_track_endpoint(track, source_url=clean_url, source_kind="track")
            return ResolveResult(kind="track", name=meta.title, tracks=[meta])

        if kind == "album":
            album = client.get_album(clean_url).to_dict()
            album_artist = ", ".join(
                a.get("name", "") for a in album.get("artists") or [] if a.get("name")
            )
            tracks = [
                _track_from_album_item(it, album, album_artist, clean_url)
                for it in album.get("tracks") or []
            ]
            return ResolveResult(
                kind="album",
                name=album.get("name") or "Unknown Album",
                tracks=tracks,
            )

        if kind == "playlist":
            # max_tracks=None fuerza la paginación completa. El valor por defecto
            # de la librería es 100 para proteger llamadas accidentales grandes.
            playlist = client.get_playlist(clean_url, max_tracks=None).to_dict()
            tracks = [
                _track_from_playlist_item(it.get("track") or it, clean_url)
                for it in playlist.get("tracks") or []
            ]
            return ResolveResult(
                kind="playlist",
                name=playlist.get("name") or "Unknown Playlist",
                tracks=tracks,
            )
    except Exception as e:
        # SpotifyScraper lanza excepciones internas con texto crudo.
        # Las traducimos a IngestError para que la API responda 422.
        msg = str(e)
        if "Failed to extract" in msg or "is not a Spotify" in msg or "not found" in msg.lower():
            raise IngestError(
                f"No se pudo resolver la URL — ¿es pública y existe? ({msg[:120]})"
            ) from e
        raise

    raise ValueError(f"Tipo desconocido: {kind}")


def fetch_track_meta(spotify_id: str) -> TrackMeta:
    """Re-fetch usado por el worker antes de descargar."""
    url = f"https://open.spotify.com/track/{spotify_id}"
    track = get_client().get_track(url).to_dict()
    return _track_meta_from_track_endpoint(track, source_url=url, source_kind="track")
