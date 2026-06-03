"""API Subsonic para bbeat.

Expone el catálogo de bbeat a través del protocolo Subsonic
(http://www.subsonic.org/pages/api.jsp), para que cualquier cliente Subsonic
—muchos en iPhone: Amperfy, play:Sub, substreamer; o Symfonium multiplataforma—
pueda navegar y reproducir la música.

Todo pasa por un único dispatcher montado en `/rest/{action}` (con o sin sufijo
`.view`): autentica con el token Subsonic del usuario, despacha al handler
correspondiente y serializa en XML/JSON/JSONP según el parámetro `f`.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import Response
from sqlmodel import Session

from app.db import get_session
from fastapi import Depends

from . import handlers, serialize
from .auth import ERR_GENERIC, SubsonicError, authenticate

log = logging.getLogger("bbeat.subsonic")

router = APIRouter(prefix="/rest", tags=["subsonic"])


async def _collect_params(request: Request) -> dict:
    """Funde query params y form (POST). Guarda el último valor de cada clave en
    `params[k]`, y TODOS los valores repetidos en `params["_lists"][k]` (Subsonic
    repite parámetros: `id`, `songId`, `songIdToAdd`, `songIndexToRemove`…)."""
    params: dict = {}
    lists: dict[str, list[str]] = {}

    def absorb(multi) -> None:
        for key in set(multi.keys()):
            vals = multi.getlist(key)
            if not vals:
                continue
            lists.setdefault(key, []).extend(vals)
            params[key] = vals[-1]

    absorb(request.query_params)
    if request.method == "POST":
        absorb(await request.form())

    params["_lists"] = lists
    params["id_list"] = lists.get("id", [])
    range_header = request.headers.get("range")
    if range_header:
        params["_range"] = range_header
    return params


@router.api_route("/{action}", methods=["GET", "POST"])
async def dispatch(
    action: str,
    request: Request,
    session: Session = Depends(get_session),
) -> Response:
    params = await _collect_params(request)
    fmt = params.get("f", "xml")
    callback = params.get("callback")

    # Normaliza la acción: "ping.view" → "ping"
    if action.endswith(".view"):
        action = action[:-5]

    try:
        user = authenticate(params, session)
        handler = handlers.HANDLERS.get(action)
        if handler is None:
            raise SubsonicError(ERR_GENERIC, f"Acción no soportada: {action}")
        result = handler(params, user, session)
    except SubsonicError as e:
        return serialize.error(e.code, e.message, fmt, callback)
    except Exception:  # noqa: BLE001
        log.exception("Error en acción Subsonic %s", action)
        return serialize.error(ERR_GENERIC, "Error interno del servidor", fmt, callback)

    # Handlers binarios (stream/download/getCoverArt) devuelven Response directo.
    if isinstance(result, Response):
        return result
    return serialize.render(result or {}, fmt, callback)
