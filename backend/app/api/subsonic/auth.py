"""Autenticación de clientes Subsonic.

Subsonic no usa cabeceras: las credenciales viajan en query params. Un cliente
manda `u=<username>` y o bien:

  - token-auth:    `t=md5(password + salt)`  + `s=<salt>`
  - password-auth: `p=<password>`  o  `p=enc:<hex(password)>`

Como el `password_hash` de bbeat es bcrypt (irreversible) NO podemos validar el
password real de la cuenta contra el esquema de token de Subsonic. En su lugar
cada usuario tiene un `subsonic_token` dedicado (secreto en claro, regenerable),
y ese es el "password" que se configura en el cliente Subsonic.
"""
from __future__ import annotations

import hashlib
import hmac

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import User


class SubsonicError(Exception):
    """Error con código Subsonic. Se captura en el dispatcher y se renderiza
    en el formato pedido (HTTP 200, error en el cuerpo)."""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


# Códigos estándar del protocolo Subsonic
ERR_GENERIC = 0
ERR_MISSING_PARAM = 10
ERR_BAD_CREDENTIALS = 40
ERR_NOT_AUTHORIZED = 50
ERR_NOT_FOUND = 70


def _decode_password(p: str) -> str:
    """`p` puede venir en claro o como `enc:<hex>`."""
    if p.startswith("enc:"):
        try:
            return bytes.fromhex(p[4:]).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return ""
    return p


def _token_matches(secret: str, token: str, salt: str) -> bool:
    expected = hashlib.md5((secret + salt).encode("utf-8")).hexdigest()
    return hmac.compare_digest(expected.lower(), (token or "").lower())


def authenticate(params: dict, session: Session) -> User:
    """Valida las credenciales Subsonic y devuelve el User, o lanza SubsonicError."""
    username = params.get("u")
    if not username:
        raise SubsonicError(ERR_MISSING_PARAM, "Falta el parámetro 'u'")

    user = session.exec(
        select(User).where(func.lower(User.username) == username.strip().lower())
    ).first()
    # No revelamos si el usuario existe: mismo error para usuario/credencial mala.
    if user is None or not user.subsonic_token:
        raise SubsonicError(ERR_BAD_CREDENTIALS, "Usuario o contraseña incorrectos")

    token = params.get("t")
    salt = params.get("s")
    password = params.get("p")

    ok = False
    if token and salt:
        ok = _token_matches(user.subsonic_token, token, salt)
    elif password is not None:
        ok = hmac.compare_digest(_decode_password(password), user.subsonic_token)
    else:
        raise SubsonicError(ERR_MISSING_PARAM, "Faltan credenciales (t+s o p)")

    if not ok:
        raise SubsonicError(ERR_BAD_CREDENTIALS, "Usuario o contraseña incorrectos")
    if not user.is_active:
        raise SubsonicError(ERR_BAD_CREDENTIALS, "Cuenta bloqueada")
    if not user.is_approved:
        raise SubsonicError(ERR_BAD_CREDENTIALS, "Cuenta pendiente de aprobación")

    return user
