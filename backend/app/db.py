from contextlib import contextmanager
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings


def _connect_args() -> dict:
    return {"check_same_thread": False}


engine = create_engine(
    f"sqlite:///{settings.db_path}",
    echo=False,
    connect_args=_connect_args(),
)


def init_db() -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    # Importar modelos para que se registren en SQLModel.metadata
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _migrate_schema()


def _migrate_schema() -> None:
    """Migraciones idempotentes (añadir columnas a tablas existentes).

    SQLModel.create_all() solo crea tablas que no existen — no toca tablas
    ya creadas con un esquema antiguo. Para añadir columnas nuevas hacemos
    ALTER TABLE manual; SQLite lo ignora si la columna ya existe (capturamos
    el error).
    """
    columns_to_add = [
        ("jobs", "progress", "INTEGER DEFAULT 0"),
        ("jobs", "stage", "TEXT"),
        ("jobs", "user_id", "INTEGER"),
        ("jobs", "target_album_id", "INTEGER"),
        ("albums", "owner_id", "INTEGER"),
        ("albums", "is_public", "INTEGER DEFAULT 0"),
        ("albums", "kind", "TEXT DEFAULT 'album'"),
        ("tracks", "external_id", "TEXT"),
        ("tracks", "source_url", "TEXT"),
        ("tracks", "has_cover", "INTEGER DEFAULT 0"),
        # Aprobación de cuentas: los usuarios que ya existían se aprueban
        # (DEFAULT 1); los nuevos los inserta el ORM con 0 (pendientes).
        ("users", "is_approved", "INTEGER NOT NULL DEFAULT 1"),
        # Token de acceso para clientes Subsonic (NULL = sin activar).
        ("users", "subsonic_token", "TEXT"),
    ]
    with engine.begin() as conn:
        for table, col, type_decl in columns_to_add:
            try:
                conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN {col} {type_decl}"
                )
            except Exception:
                pass
        # Backfill: Track.external_id desde Jobs done
        try:
            conn.exec_driver_sql(
                "UPDATE tracks SET external_id = ("
                "  SELECT j.spotify_track_id FROM jobs j"
                "  WHERE j.result_track_id = tracks.id"
                "  AND j.status = 'done'"
                "  LIMIT 1"
                ") WHERE external_id IS NULL"
            )
        except Exception as e:
            import logging
            logging.warning("backfill external_id falló: %s", e)
        # Backfill: AlbumTrack desde Track.album_id si la tabla está vacía
        try:
            row = conn.exec_driver_sql("SELECT COUNT(*) FROM album_tracks").first()
            if row and row[0] == 0:
                conn.exec_driver_sql(
                    "INSERT INTO album_tracks (album_id, track_id, position, added_at) "
                    "SELECT album_id, id, track_number, CURRENT_TIMESTAMP FROM tracks "
                    "WHERE album_id IS NOT NULL"
                )
        except Exception as e:
            import logging
            logging.warning("backfill album_tracks falló: %s", e)
        # Backfill: marcar como 'playlist' los álbumes cuyo artista es Various Artists.
        try:
            conn.exec_driver_sql(
                "UPDATE albums SET kind = 'playlist' WHERE kind != 'playlist' "
                "AND artist_id IN (SELECT id FROM artists WHERE name_normalized = 'various artists')"
            )
        except Exception as e:
            import logging
            logging.warning("backfill album.kind falló: %s", e)
        # Backfill: auto-guardar a cada dueño sus álbumes existentes, para que la
        # pestaña 'Guardados' no salga vacía al estrenar el modelo de guardados.
        try:
            row = conn.exec_driver_sql("SELECT COUNT(*) FROM album_saves").first()
            if row and row[0] == 0:
                conn.exec_driver_sql(
                    "INSERT OR IGNORE INTO album_saves (user_id, album_id, created_at) "
                    "SELECT owner_id, id, CURRENT_TIMESTAMP FROM albums "
                    "WHERE owner_id IS NOT NULL"
                )
        except Exception as e:
            import logging
            logging.warning("backfill album_saves falló: %s", e)


@contextmanager
def session_scope() -> Iterator[Session]:
    s = Session(engine)
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_scope() as s:
        yield s
