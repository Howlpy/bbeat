"""Escritura de géneros respetando bloqueos, y coherencia por artista.

El género vive en el TAG del fichero además de en la BD: el scanner reconstruye
`tracks.genre` desde el tag, así que todo cambio automático escribe primero el
tag (si falla, la BD no se toca) igual que scripts/backfill_genres.py.

genre_locked = True significa "lo puso una persona": ningún proceso automático
(IA, backfill) lo cambia. Solo una edición manual puede.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Callable, Optional

from sqlmodel import Session, select

from app.config import settings
from app.models import Artist, Track

log = logging.getLogger("bbeat.genres")

# Coherencia por artista: con al menos MIN_TRACKS pistas y MIN_SHARE de acuerdo.
CONSISTENCY_MIN_TRACKS = 3
CONSISTENCY_MIN_SHARE = 0.8
# Evidencia fuerte de pista suelta: su álbum ya tiene este nº de pistas con ese género.
STRONG_ALBUM_VOTES = 2


def write_genre_tag(rel_path: str, genre: str) -> Optional[str]:
    """Escribe el tag de género. Devuelve el error, o None si fue bien."""
    import mutagen

    path = settings.music_dir / rel_path
    if not path.is_file():
        return "el fichero no está en disco"
    try:
        audio = mutagen.File(path, easy=True)
        if audio is None:
            return "no es un fichero de audio reconocible"
        if audio.tags is None:
            audio.add_tags()
        audio["genre"] = genre
        audio.save()
    except Exception as e:
        return str(e)
    return None


def set_track_genre(
    session: Session,
    track: Track,
    genre: str,
    source: str,
    *,
    lock: bool = False,
    write_tag: Optional[Callable[[str, str], Optional[str]]] = None,
) -> bool:
    """Cambia el género de una pista (tag + BD). False si no se cambió.

    Un proceso automático (source != 'manual') nunca toca una pista bloqueada.
    No hace commit: lo hace quien llama.
    """
    if track.genre_locked and source != "manual":
        return False
    if track.genre != genre:
        err = (write_tag or write_genre_tag)(track.file_path, genre)
        if err:
            log.warning("género no escrito en %s: %s", track.file_path, err)
            return False
        track.genre = genre
    track.genre_source = source
    if lock:
        track.genre_locked = True
    session.add(track)
    return True


def artist_distribution(session: Session, artist_id: int) -> Counter:
    """Género (en minúsculas) -> nº de pistas del artista. Sin género no cuenta."""
    rows = session.exec(select(Track.genre).where(Track.artist_id == artist_id)).all()
    c: Counter = Counter()
    for g in rows:
        g = (g or "").strip().lower()
        if g:
            c[g] += 1
    return c


def dominant_genre(dist: Counter) -> Optional[tuple[str, float]]:
    total = sum(dist.values())
    if not total:
        return None
    g, n = dist.most_common(1)[0]
    return g, n / total


def apply_artist_consistency(
    session: Session, artist_name: str, new_genre: Optional[str], album: Optional[str] = None
) -> tuple[Optional[str], bool]:
    """Ajusta el género de una pista NUEVA al de su artista.

    Si el artista ya tiene >=3 pistas y >=80% comparten un género distinto del
    resuelto, se conserva el del artista, salvo evidencia fuerte: el álbum de la
    pista ya tiene >=2 pistas con el género nuevo. Devuelve (género, conflicto):
    conflicto=True si el resuelto discrepaba del artista.
    """
    if not new_genre or not settings.artist_consistency:
        return new_genre, False
    normalized = re.sub(r"\s+", " ", (artist_name or "").strip().lower())
    artist = session.exec(select(Artist).where(Artist.name_normalized == normalized)).first()
    if artist is None:
        return new_genre, False
    dist = artist_distribution(session, artist.id)
    dom = dominant_genre(dist)
    if dom is None or sum(dist.values()) < CONSISTENCY_MIN_TRACKS or dom[1] < CONSISTENCY_MIN_SHARE:
        return new_genre, False
    top = dom[0]
    if new_genre.strip().lower() == top:
        return new_genre, False
    if album:
        from app.models import Album

        n = session.exec(
            select(Track.id)
            .join(Album, Album.id == Track.album_id)
            .where(
                Track.artist_id == artist.id,
                Album.title_normalized == re.sub(r"\s+", " ", album.strip().lower()),
                Track.genre == new_genre,
            )
        ).all()
        if len(n) >= STRONG_ALBUM_VOTES:
            return new_genre, True
    return top, True
