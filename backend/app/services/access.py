"""Filtros de visibilidad por usuario, conscientes de AlbumTrack (M:N)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import or_
from sqlmodel import Session, select

from app.models import Album, AlbumTrack, Track, User


def visible_album_ids(session: Session, user: Optional[User]) -> list[int]:
    """IDs de álbumes que el usuario puede ver. Admin → todos."""
    if user is None:
        return []
    if user.is_admin:
        return list(session.exec(select(Album.id)).all())
    return list(
        session.exec(
            select(Album.id).where(
                or_(Album.owner_id == user.id, Album.is_public == True)  # noqa: E712
            )
        ).all()
    )


def visible_track_ids_subquery(user: Optional[User]):
    """Subquery (select de track_id) con todos los tracks que el user puede ver.

    Un track es visible si pertenece (vía AlbumTrack) a algún álbum visible,
    o si no tiene álbum asignado (legacy).
    """
    if user is None:
        return None
    if user.is_admin:
        # admin → todos los track ids (cualquier track)
        return select(Track.id)
    # IDs de álbumes visibles
    visible_albs = select(Album.id).where(
        or_(Album.owner_id == user.id, Album.is_public == True)  # noqa: E712
    )
    # tracks que están en al menos un álbum visible
    via_membership = select(AlbumTrack.track_id).where(AlbumTrack.album_id.in_(visible_albs))
    # tracks huérfanos (sin album_id)
    orphan = select(Track.id).where(Track.album_id == None)  # noqa: E711
    return via_membership.union(orphan)


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
    """¿El user tiene acceso de lectura/stream a este track?"""
    if user.is_admin:
        return True
    # cualquier álbum visible que contenga el track
    q = (
        select(Album.id)
        .join(AlbumTrack, AlbumTrack.album_id == Album.id)
        .where(AlbumTrack.track_id == track_id)
        .where(or_(Album.owner_id == user.id, Album.is_public == True))  # noqa: E712
        .limit(1)
    )
    if session.exec(q).first():
        return True
    # huérfano
    t = session.get(Track, track_id)
    if t and t.album_id is None:
        return True
    return False
