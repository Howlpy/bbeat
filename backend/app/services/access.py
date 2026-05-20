"""Filtros de visibilidad por usuario.

Reglas:
- Admin: ve todo, puede modificar todo.
- Usuario regular: ve sus álbumes + álbumes is_public=True. Solo modifica los suyos.
- Tracks: visibles si su álbum es visible.
- Tracks sin album_id (raros): visibles para todos (legacy/uploads sueltos).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import or_
from sqlmodel import Session, select

from app.models import Album, Track, User


def visible_album_ids(session: Session, user: Optional[User]) -> set[int]:
    """IDs de álbumes que el usuario puede ver. None=todos."""
    if user is None:
        return set()
    if user.is_admin:
        ids = session.exec(select(Album.id)).all()
        return set(ids)
    ids = session.exec(
        select(Album.id).where(or_(Album.owner_id == user.id, Album.is_public == True))  # noqa: E712
    ).all()
    return set(ids)


def visibility_filter_for_tracks(user: Optional[User]):
    """Condición SQL para filtrar tracks por visibilidad.

    Devuelve una expresión que se puede pasar a .where(). Admin → True trivial.
    """
    if user and user.is_admin:
        return True
    # Track sin album → visible para todos
    # Track con album → debe ser del user o público
    if user is None:
        # No auth, solo álbumes públicos
        return or_(Track.album_id == None, Album.is_public == True)  # noqa: E712, E711
    return or_(
        Track.album_id == None,  # noqa: E711
        Album.is_public == True,  # noqa: E712
        Album.owner_id == user.id,
    )


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
