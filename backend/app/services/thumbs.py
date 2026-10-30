"""Miniaturas de carátulas, generadas bajo demanda y cacheadas en disco.

Las listas pintan carátulas de 40 px; servir el original (cientos de KB) es
puro desperdicio de red. La miniatura se guarda en data/thumbs con una clave
que incluye ruta, mtime y tamaño del original: si la carátula cambia, la clave
cambia y no hay que invalidar nada a mano.
"""
from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from app.config import settings

log = logging.getLogger("bbeat.thumbs")

_warned: set[str] = set()

# Anchos permitidos: 96 (filas de 40-48 px a 2x), 192 y 384 (tarjetas de rejilla).
THUMB_SIZES = (96, 192, 384)


def snap_width(w: Optional[int]) -> Optional[int]:
    """Menor ancho permitido >= w. None si no se pide miniatura o w supera el máximo."""
    if not w or w <= 0:
        return None
    for size in THUMB_SIZES:
        if w <= size:
            return size
    return None


def thumb_for(src: Path, w: int) -> tuple[Optional[Path], bool]:
    """Miniatura WebP de `src` a ancho `w`, creándola si no existe.

    Devuelve (ruta, fallo). Ruta None = servir el original; fallo True si fue
    por un error (no porque el original ya sea pequeño), para no cachearlo
    como definitivo.
    """
    try:
        st = src.stat()
        key = hashlib.sha1(f"{src.name}|{st.st_mtime_ns}|{st.st_size}|{w}".encode()).hexdigest()
        out = settings.data_dir / "thumbs" / f"{key}.webp"
        if out.is_file():
            return out, False
        from PIL import Image

        with Image.open(src) as im:
            if im.width <= w:
                return None, False
            im.thumbnail((w, w), Image.LANCZOS)
            im = im.convert("RGB")
            out.parent.mkdir(parents=True, exist_ok=True)
            # Temporal único: dos peticiones simultáneas no pisan el mismo fichero.
            fd, tmp_name = tempfile.mkstemp(dir=out.parent, prefix=f"{key}.", suffix=".tmp")
            os.close(fd)
            tmp = Path(tmp_name)
            try:
                im.save(tmp, "WEBP", quality=80, method=4)
                os.replace(tmp, out)
            finally:
                tmp.unlink(missing_ok=True)
        return out, False
    except Exception as e:  # noqa: BLE001 — cualquier fallo cae al original
        if str(src) not in _warned:  # una vez por fichero
            _warned.add(str(src))
            log.warning("miniatura de %s falló: %s", src, e)
        return None, True
