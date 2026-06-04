"""Presencia "sonando ahora" en memoria.

Registro efímero de qué está escuchando cada usuario en este momento, para el
feed en vivo de `/live` (vía SSE). Es a propósito **volátil y en memoria**: bbeat
corre con un único worker (ver `app/main.py`), así que un dict en proceso basta y
no necesitamos Redis ni persistencia — si el server reinicia, la presencia se
reconstruye sola con los siguientes heartbeats/scrobbles.

Cada entrada caduca por TTL: el player web manda heartbeats periódicos y los
clientes Subsonic se registran al hacer now-playing/stream. Si dejan de llegar,
la entrada expira y el usuario desaparece del feed.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Optional

# TTLs (segundos) según la fuente del evento.
TTL_WEB = 40           # heartbeat del player web cada ~25s
TTL_SUBSONIC_NOW = 300  # notificación now-playing (scrobble?submission=false)
TTL_SUBSONIC_STREAM_MAX = 600  # tope para presencia derivada de /rest/stream

_LOCK = threading.Lock()
_PRESENCE: dict[int, dict[str, Any]] = {}


def touch(
    user_id: int,
    username: str,
    track: dict,
    source: str,
    ttl_seconds: float,
) -> None:
    """Marca (o refresca) que `user_id` está escuchando `track`.

    `track` es un payload ya serializado (ver `_track_payload` en library.py).
    Si la pista no cambia respecto a la entrada previa se conserva `started_at`,
    para que el "hace X" del cliente no se reinicie en cada heartbeat.
    """
    now = time.time()
    track_id = track.get("id")
    with _LOCK:
        prev = _PRESENCE.get(user_id)
        if prev and prev["track"].get("id") == track_id and prev["source"] == source:
            started_at = prev["started_at"]
        else:
            started_at = datetime.utcnow().isoformat()
        _PRESENCE[user_id] = {
            "user_id": user_id,
            "username": username,
            "source": source,
            "track": track,
            "started_at": started_at,
            "_updated": now,
            "_expires": now + ttl_seconds,
        }


def clear(user_id: int) -> None:
    """Quita a `user_id` del feed (al pausar/parar)."""
    with _LOCK:
        _PRESENCE.pop(user_id, None)


def snapshot() -> list[dict]:
    """Lista de presencias vivas (purga expiradas), más reciente primero.

    Devuelve dicts listos para serializar (sin los campos internos `_*`).
    """
    now = time.time()
    with _LOCK:
        expired = [uid for uid, e in _PRESENCE.items() if e["_expires"] <= now]
        for uid in expired:
            _PRESENCE.pop(uid, None)
        entries = sorted(_PRESENCE.values(), key=lambda e: e["_updated"], reverse=True)
    return [
        {
            "user_id": e["user_id"],
            "username": e["username"],
            "source": e["source"],
            "started_at": e["started_at"],
            "track": e["track"],
        }
        for e in entries
    ]
