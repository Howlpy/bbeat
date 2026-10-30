"""Aislamiento de los tests: todo el estado va a un directorio temporal.

Las variables se fijan ANTES de importar cualquier módulo de app (settings se
lee al importar), y db_path/secrets_dir no siguen a BBEAT_DATA_DIR, así que se
fijan una a una. Nunca se toca data/ real.
"""
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="bbeat-tests-"))
for _k, _v in {
    "BBEAT_DATA_DIR": _TMP,
    "BBEAT_MUSIC_DIR": _TMP / "music",
    "BBEAT_COVERS_DIR": _TMP / "covers",
    "BBEAT_TRANSCACHE_DIR": _TMP / "transcache",
    "BBEAT_DB_PATH": _TMP / "library.db",
    "BBEAT_SECRETS_DIR": _TMP / "secrets",
}.items():
    os.environ[_k] = str(_v)
