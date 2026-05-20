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
    ]
    with engine.begin() as conn:
        for table, col, type_decl in columns_to_add:
            try:
                conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN {col} {type_decl}"
                )
            except Exception:
                # Columna ya existente, ignoramos
                pass


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
