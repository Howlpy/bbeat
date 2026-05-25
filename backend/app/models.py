from datetime import datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


def _now() -> datetime:
    return datetime.utcnow()


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    email: str = Field(index=True, unique=True)
    password_hash: str = Field()
    is_admin: bool = Field(default=False, index=True)
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=_now)


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
    owner_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    # 'album' = lanzamiento de un único artista; 'playlist' = colección multi-artista.
    kind: str = Field(default="album", index=True)
    # Deprecado: el modelo público/privado se retiró (pool global). Se conserva la
    # columna para no romper el esquema antiguo, pero ya no se usa en ninguna lógica.
    is_public: bool = Field(default=False, index=True)
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
    # Identificador externo del provider para dedup (spotify_id raw, yt:..., sc:...)
    external_id: Optional[str] = Field(default=None, index=True)
    # URL exacta del vídeo/track del que se descargó (para verificar match)
    source_url: Optional[str] = Field(default=None)

    # True si hay carátula propia de la pista en covers/track-{id}.{jpg,png}
    has_cover: bool = Field(default=False)

    file_path: str = Field(unique=True, index=True)
    file_size: Optional[int] = Field(default=None)
    file_format: Optional[str] = Field(default=None)
    bitrate: Optional[int] = Field(default=None)
    sample_rate: Optional[int] = Field(default=None)

    last_scanned: datetime = Field(default_factory=_now)
    created_at: datetime = Field(default_factory=_now)

    artist: Optional[Artist] = Relationship(back_populates="tracks")
    album: Optional[Album] = Relationship(back_populates="tracks")


class AlbumTrack(SQLModel, table=True):
    """Asociación M:N entre álbumes y pistas.

    Permite que una misma pista (un único fichero en disco) pertenezca a varios
    álbumes — por ejemplo, el álbum "original" + un álbum de colección de un user.
    """
    __tablename__ = "album_tracks"

    album_id: int = Field(foreign_key="albums.id", primary_key=True)
    track_id: int = Field(foreign_key="tracks.id", primary_key=True)
    position: Optional[int] = Field(default=None)  # número de orden en el álbum
    added_at: datetime = Field(default_factory=_now)


class AlbumSave(SQLModel, table=True):
    """Álbum/playlist guardado por un usuario en su biblioteca.

    El catálogo de álbumes es un pool global (cualquiera ve todo); 'guardar'
    es lo que decide qué aparece en la sección personal de cada usuario.
    """
    __tablename__ = "album_saves"

    user_id: int = Field(foreign_key="users.id", primary_key=True)
    album_id: int = Field(foreign_key="albums.id", primary_key=True)
    created_at: datetime = Field(default_factory=_now)


class TrackLike(SQLModel, table=True):
    """'Me gusta' de un usuario sobre una pista (tipo Spotify)."""
    __tablename__ = "track_likes"

    user_id: int = Field(foreign_key="users.id", primary_key=True)
    track_id: int = Field(foreign_key="tracks.id", primary_key=True)
    created_at: datetime = Field(default_factory=_now)


class Play(SQLModel, table=True):
    """Un evento de reproducción (para historial + más escuchadas)."""
    __tablename__ = "plays"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    track_id: int = Field(foreign_key="tracks.id", index=True)
    played_at: datetime = Field(default_factory=_now, index=True)


class Setting(SQLModel, table=True):
    """Pares clave/valor editables desde la UI (override del .env)."""
    __tablename__ = "settings"

    key: str = Field(primary_key=True)
    value: str = Field(default="")
    updated_at: datetime = Field(default_factory=_now)


class Job(SQLModel, table=True):
    """Trabajo de ingesta: una pista a descargar desde una URL de Spotify."""
    __tablename__ = "jobs"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Origen: la URL/colección que el usuario pegó. Misma para todos
    # los tracks de una playlist/álbum, así puedo agruparlos en UI.
    source_url: str = Field(index=True)
    source_kind: str = Field(default="track")  # track | album | playlist

    # Quién inició este job (None = legacy / sistema)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    target_album_id: Optional[int] = Field(default=None, foreign_key="albums.id")

    # Metadata Spotify resuelta (capturada al CREAR el job, no se re-fetchea)
    spotify_track_id: str = Field(unique=True, index=True)
    title: str = ""
    artist: str = ""           # primer artista para display
    artists_csv: str = ""      # todos los artistas separados por ", "
    album_artist: str = ""
    album: str = ""
    track_number: int = Field(default=1)
    disc_number: int = Field(default=1)
    total_tracks: int = Field(default=1)
    duration_ms: Optional[int] = Field(default=None)
    year: Optional[int] = Field(default=None)
    cover_url: Optional[str] = Field(default=None)

    # Estado
    status: str = Field(default="pending", index=True)
    # pending | running | done | failed | skipped (ya existía)
    progress: int = Field(default=0)            # 0-100, solo válido mientras running
    stage: Optional[str] = Field(default=None)  # descarga | tags | etc.
    backend_used: Optional[str] = Field(default=None)  # votify | yt-dlp
    error: Optional[str] = Field(default=None)
    result_track_id: Optional[int] = Field(
        default=None, foreign_key="tracks.id"
    )

    created_at: datetime = Field(default_factory=_now)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
