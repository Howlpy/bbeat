from datetime import datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


def _now() -> datetime:
    return datetime.utcnow()


class Artist(SQLModel, table=True):
    __tablename__ = "artists"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    name_normalized: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=_now)

    albums: list["Album"] = Relationship(back_populates="artist")
    tracks: list["Track"] = Relationship(back_populates="artist")


class Album(SQLModel, table=True):
    __tablename__ = "albums"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    title_normalized: str = Field(index=True)
    artist_id: int = Field(foreign_key="artists.id", index=True)
    year: Optional[int] = Field(default=None, index=True)
    cover_path: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=_now)

    artist: Optional[Artist] = Relationship(back_populates="albums")
    tracks: list["Track"] = Relationship(back_populates="album")


class Track(SQLModel, table=True):
    __tablename__ = "tracks"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    artist_id: int = Field(foreign_key="artists.id", index=True)
    album_id: Optional[int] = Field(default=None, foreign_key="albums.id", index=True)
    track_number: Optional[int] = Field(default=None)
    disc_number: Optional[int] = Field(default=None)
    duration_ms: Optional[int] = Field(default=None)

    file_path: str = Field(unique=True, index=True)
    file_size: Optional[int] = Field(default=None)
    file_format: Optional[str] = Field(default=None)
    bitrate: Optional[int] = Field(default=None)
    sample_rate: Optional[int] = Field(default=None)

    last_scanned: datetime = Field(default_factory=_now)
    created_at: datetime = Field(default_factory=_now)

    artist: Optional[Artist] = Relationship(back_populates="tracks")
    album: Optional[Album] = Relationship(back_populates="tracks")


class Setting(SQLModel, table=True):
    """Pares clave/valor editables desde la UI (override del .env)."""
    __tablename__ = "settings"

    key: str = Field(primary_key=True)
    value: str = Field(default="")
    updated_at: datetime = Field(default_factory=_now)
