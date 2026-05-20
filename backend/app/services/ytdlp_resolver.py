"""Resuelve metadata de URLs de YouTube/SoundCloud usando yt-dlp.

A diferencia de SpotifyScraper, aquí el "ID del track" no existe como tal —
usamos un prefijo (`yt:` o `sc:`) + el ID de yt-dlp para garantizar unicidad.
"""
from __future__ import annotations

import logging
from typing import Optional

from yt_dlp import YoutubeDL

from app.services.spotify import IngestError, ResolveResult, TrackMeta
from app.services.sources import SourceKind

log = logging.getLogger("bbeat.ytdlp_resolver")


def _provider_prefix(kind: SourceKind) -> str:
    return {"youtube": "yt", "soundcloud": "sc"}.get(kind, "url")


def _normalize_for_compare(s: str) -> str:
    import re as _re
    return _re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _split_artist_title(raw_title: str, artist: str) -> tuple[str, str]:
    """Si el título viene como 'Artista - Canción' (o variantes con — / · / |)
    y el artista detectado coincide con la primera parte, devolvemos solo
    la canción. Si no podemos partirlo con confianza, devolvemos tal cual.
    """
    import re as _re
    # Quitar sufijos típicos de YouTube
    cleaned = _re.sub(
        r"\s*[\(\[](?:official\s*(?:video|music\s*video|audio)|lyrics?|hd|4k\s*remaster(?:ed)?|remaster(?:ed)?\s*\d{4}|video\s*oficial)\s*[\)\]]\s*$",
        "",
        raw_title,
        flags=_re.IGNORECASE,
    ).strip()

    # Probar separadores comunes
    for sep in [" - ", " – ", " — ", " · ", " | ", " // "]:
        if sep in cleaned:
            left, _, right = cleaned.partition(sep)
            left_norm = _normalize_for_compare(left)
            artist_norm = _normalize_for_compare(artist)
            # Si el lado izquierdo coincide aproximadamente con el artista, quedarnos con el derecho
            if left_norm and artist_norm and (
                left_norm == artist_norm
                or left_norm in artist_norm
                or artist_norm in left_norm
            ):
                return right.strip(), artist
            # Si no coincide, probablemente el formato es "Artista - Título"
            # pero con un artista distinto al uploader. Cogemos derecho como título.
            return right.strip(), left.strip()
    return cleaned, artist


def _track_meta_from_entry(
    entry: dict,
    idx: int,
    total: int,
    source_url: str,
    source_kind: SourceKind,
    fallback_album: str = "",
) -> TrackMeta:
    """Convierte un entry de yt-dlp a TrackMeta."""
    raw_title = entry.get("title") or entry.get("alt_title") or "Unknown"
    # Como "artista" usamos uploader/channel/artist
    raw_artist = (
        entry.get("artist")
        or entry.get("uploader")
        or entry.get("channel")
        or "Unknown Artist"
    )
    title, artist = _split_artist_title(raw_title, raw_artist)
    # Limpieza adicional: quitar "- Topic" del final del artista (canal auto-generado)
    artist = artist.replace(" - Topic", "").strip()
    track_id = entry.get("id") or entry.get("display_id") or raw_title
    prefix = _provider_prefix(source_kind)

    # Spotify devuelve cover en album.images; aquí el thumbnail viene plano
    cover = entry.get("thumbnail")
    # Si trae varias thumbnails, coge la mayor
    if not cover and entry.get("thumbnails"):
        sorted_thumbs = sorted(
            entry["thumbnails"],
            key=lambda t: (t.get("width") or 0) * (t.get("height") or 0),
            reverse=True,
        )
        if sorted_thumbs:
            cover = sorted_thumbs[0].get("url")

    dur = entry.get("duration") or 0  # seconds
    return TrackMeta(
        spotify_id=f"{prefix}:{track_id}",
        title=title,
        artists=[artist],
        album=fallback_album,
        album_artist=artist,
        track_number=idx,
        disc_number=1,
        total_tracks=total,
        duration_ms=int(dur * 1000),
        isrc=None,
        year=entry.get("release_year") or _year_from_release_date(entry.get("release_date")),
        cover_url=cover,
        source_url=entry.get("webpage_url") or entry.get("url") or source_url,
        source_kind=source_kind,
    )


def _year_from_release_date(date) -> Optional[int]:
    import re as _re
    if not date:
        return None
    m = _re.search(r"\d{4}", str(date))
    return int(m.group()) if m else None


def resolve_url(url: str, source_kind: SourceKind) -> ResolveResult:
    """Extrae metadata sin descargar. Maneja single y playlist/set."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "discard_in_playlist",
        "ignoreerrors": False,
        "socket_timeout": 30,
    }
    log.info("resolviendo %s · %s", source_kind, url)
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        msg = str(e)
        raise IngestError(f"No se pudo resolver la URL ({msg[:150]})") from e

    if not info:
        raise IngestError("La URL no devolvió contenido")

    is_playlist = info.get("_type") == "playlist" or bool(info.get("entries"))

    if is_playlist:
        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            raise IngestError("La playlist/set está vacía o no es accesible")
        playlist_title = info.get("title") or "Playlist"
        tracks = [
            _track_meta_from_entry(
                e, i + 1, len(entries), info.get("webpage_url") or url, source_kind, ""
            )
            for i, e in enumerate(entries)
        ]
        return ResolveResult(kind="playlist", name=playlist_title, tracks=tracks)

    # Single track/video
    meta = _track_meta_from_entry(info, 1, 1, url, source_kind, "")
    return ResolveResult(kind="track", name=meta.title, tracks=[meta])
