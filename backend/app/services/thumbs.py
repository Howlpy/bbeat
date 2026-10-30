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
from pathlib import Path
from typing import Optional

from app.config import settings

log = logging.getLogger("bbeat.thumbs")

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


def thumb_for(src: Path, w: int) -> Optional[Path]:
    """Ruta de la miniatura WebP de `src` a ancho `w`, creándola si no existe.

    Devuelve None si no hace falta (el original ya es pequeño) o si algo falla:
    el llamador sirve entonces el original.
    """
    try:
        st = src.stat()
        key = hashlib.sha1(f"{src.name}|{st.st_mtime_ns}|{st.st_size}|{w}".encode()).hexdigest()
        out = settings.data_dir / "thumbs" / f"{key}.webp"
        if out.is_file():
            return out
        from PIL import Image

        with Image.open(src) as im:
            if im.width <= w:
                return None
            im.thumbnail((w, w), Image.LANCZOS)
            im = im.convert("RGB")
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_name(f"{out.name}.{os.getpid()}.tmp")
            im.save(tmp, "WEBP", quality=80, method=4)
        os.replace(tmp, out)
        return out
    except Exception as e:  # noqa: BLE001 — cualquier fallo cae al original
        log.debug("miniatura de %s falló: %s", src, e)
        return None
