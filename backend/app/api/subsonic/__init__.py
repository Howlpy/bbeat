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
    """Funde query params y form (POST), preservando los `id` repetidos."""
    params: dict = {}
    for key in request.query_params:
        params[key] = request.query_params[key]
    id_list = list(request.query_params.getlist("id"))

    if request.method == "POST":
        form = await request.form()
        for key in form:
            params[key] = form[key]
        id_list += list(form.getlist("id"))

    params["id_list"] = id_list
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
