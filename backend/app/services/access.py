"""Permisos de mutación por usuario.

La LECTURA del catálogo es un pool global: cualquier usuario autenticado ve y
reproduce todo (pistas, álbumes y playlists). Lo que decide qué aparece en la
biblioteca personal de cada uno es 'guardar' (AlbumSave), no la visibilidad.
La MUTACIÓN (editar/borrar/añadir pistas) sigue restringida a dueño o admin.
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session, select

from app.models import Album, Track, User


def visible_album_ids(session: Session, user: Optional[User]) -> list[int]:
    """Pool global: cualquier usuario ve todos los álbumes."""
    if user is None:
        return []
    return list(session.exec(select(Album.id)).all())


def visible_track_ids_subquery(user: Optional[User]):
    """Subquery con todos los track_id (pool global)."""
    if user is None:
        return None
    return select(Track.id)


def can_mutate_album(album: Album, user: User) -> bool:
    if user.is_admin:
        return True
    return album.owner_id == user.id


def can_mutate_track(album: Optional[Album], user: User) -> bool:
    if user.is_admin:
        return True
    if album is None:
        return True  # track huérfano lo edita cualquiera autenticado
    return album.owner_id == user.id


def can_access_track(session: Session, track_id: int, user: User) -> bool:
    """Lectura/stream: pool global, cualquier usuario autenticado tiene acceso."""
    return True
