"""Serialización de respuestas Subsonic (XML / JSON / JSONP).

El protocolo Subsonic envuelve toda respuesta en un objeto raíz
`subsonic-response`. Por defecto responde XML; con `f=json` responde JSON y con
`f=jsonp` JSON envuelto en una llamada `callback(...)`.

Cada handler de bbeat devuelve un **dict** que modela el CUERPO de la respuesta
(p.ej. `{"artists": {...}}`). Aquí lo metemos en el envelope y lo emitimos en el
formato pedido. Convención de mapeo dict↔XML que sigue el JSON oficial de
Subsonic:

- claves con valor escalar (str/int/float/bool/None) → **atributos** del elemento
- claves con valor dict   → **un** elemento hijo con ese nombre
- claves con valor lista  → **N** elementos hijos repetidos con ese nombre
- la clave especial "value" → **texto** del elemento (para getLyrics, error, …)
"""
from __future__ import annotations

import json as _json
from xml.sax.saxutils import escape, quoteattr

from fastapi import Response

API_VERSION = "1.16.1"
SERVER_VERSION = "bbeat"

_XML_NS = "http://subsonic.org/restapi"


def _is_scalar(v) -> bool:
    return v is None or isinstance(v, (str, int, float, bool))


def _xml_attr(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _dict_to_xml(name: str, obj: dict) -> str:
    """Convierte un dict en un elemento XML <name ...>...</name>."""
    attrs = []
    children = []
    text = None
    for key, val in obj.items():
        if key == "value":
            text = val
        elif _is_scalar(val):
            if val is None:
                continue
            attrs.append(f"{key}={quoteattr(_xml_attr(val))}")
        elif isinstance(val, dict):
            children.append(_dict_to_xml(key, val))
        elif isinstance(val, (list, tuple)):
            for item in val:
                if isinstance(item, dict):
                    children.append(_dict_to_xml(key, item))
                elif item is not None:
                    children.append(f"<{key}>{escape(str(item))}</{key}>")
    attr_str = (" " + " ".join(attrs)) if attrs else ""
    if not children and text is None:
        return f"<{name}{attr_str}/>"
    inner = "".join(children)
    if text is not None:
        inner += escape(str(text))
    return f"<{name}{attr_str}>{inner}</{name}>"


def _envelope(body: dict, *, ok: bool = True) -> dict:
    root = {
        "status": "ok" if ok else "failed",
        "version": API_VERSION,
        "type": SERVER_VERSION,
        "serverVersion": SERVER_VERSION,
        "openSubsonic": True,
    }
    root.update(body or {})
    return root


def render(body: dict, fmt: str, callback: str | None = None, *, ok: bool = True) -> Response:
    """Renderiza el cuerpo de respuesta en el formato pedido (`f` param)."""
    root = _envelope(body, ok=ok)
    fmt = (fmt or "xml").lower()

    if fmt in ("json", "jsonp"):
        payload = _json.dumps({"subsonic-response": root}, ensure_ascii=False)
        if fmt == "jsonp" and callback:
            return Response(
                content=f"{callback}({payload});",
                media_type="application/javascript; charset=utf-8",
            )
        return Response(content=payload, media_type="application/json; charset=utf-8")

    # XML (default)
    root_with_ns = {"xmlns": _XML_NS, **root}
    xml = '<?xml version="1.0" encoding="UTF-8"?>' + _dict_to_xml(
        "subsonic-response", root_with_ns
    )
    return Response(content=xml, media_type="application/xml; charset=utf-8")


def error(code: int, message: str, fmt: str, callback: str | None = None) -> Response:
    """Respuesta de error Subsonic (HTTP 200; el error va en el cuerpo)."""
    return render(
        {"error": {"code": code, "message": message}},
        fmt,
        callback,
        ok=False,
    )
