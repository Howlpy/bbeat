"""Hashing de passwords, JWT, dependency current_user."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func
from sqlmodel import Session, select

from app.config import settings
from app.db import get_session, session_scope
from app.models import User

log = logging.getLogger("bbeat.auth")

JWT_ALGO = "HS256"
JWT_EXPIRY = timedelta(days=30)

_jwt_secret: Optional[str] = None


def _jwt_secret_path():
    return settings.secrets_dir / "jwt.key"


def jwt_secret() -> str:
    """Carga (o genera) la clave para firmar JWT."""
    global _jwt_secret
    if _jwt_secret is not None:
        return _jwt_secret
    path = _jwt_secret_path()
    if path.exists():
        _jwt_secret = path.read_text().strip()
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        _jwt_secret = secrets.token_urlsafe(64)
        path.write_text(_jwt_secret)
        try:
            import os
            os.chmod(path, 0o600)
        except OSError:
            pass
        log.info("JWT secret generado y guardado en %s", path)
    return _jwt_secret


# ─── Passwords ────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ─── JWT ──────────────────────────────────────────────────────


def create_token(user_id: int, username: str, is_admin: bool) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "is_admin": is_admin,
        "iat": int(now.timestamp()),
        "exp": int((now + JWT_EXPIRY).timestamp()),
    }
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGO)


def decode_token(token: str) -> dict:
    return jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGO])


# ─── FastAPI dependencies ────────────────────────────────────


bearer = HTTPBearer(auto_error=False)


def _read_token(request: Request, creds: Optional[HTTPAuthorizationCredentials]) -> Optional[str]:
    if creds and creds.scheme.lower() == "bearer":
        return creds.credentials
    # Permitir también ?token=xxx (útil para <audio src> que no manda Authorization)
    qtoken = request.query_params.get("token")
    if qtoken:
        return qtoken
    return None


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> User:
    token = _read_token(request, creds)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token requerido")
    try:
        payload = decode_token(token)
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"token inválido: {e}")
    user = session.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "usuario no existe")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "cuenta bloqueada")
    return user


def get_current_user_optional(
    request: Request,
    session: Session = Depends(get_session),
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> Optional[User]:
    """Como get_current_user pero no falla si no hay token (devuelve None)."""
    token = _read_token(request, creds)
    if not token:
        return None
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        return None
    user = session.get(User, int(payload["sub"]))
    if user and user.is_active:
        return user
    return None


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "necesita ser admin")
    return user


# ─── Helpers ──────────────────────────────────────────────────


def count_users() -> int:
    with session_scope() as s:
        return len(s.exec(select(User)).all())


def find_user_by_login(login: str) -> Optional[User]:
    """Busca por username (sin distinguir mayúsculas) o email."""
    login = login.strip().lower()
    with session_scope() as s:
        u = s.exec(
            select(User).where(
                (func.lower(User.username) == login) | (User.email == login)
            )
        ).first()
        if u:
            s.expunge(u)
        return u


def create_user(
    username: str,
    email: str,
    password: str,
    is_admin: bool = False,
) -> User:
    with session_scope() as s:
        user = User(
            username=username.strip(),
            email=email.strip().lower(),
            password_hash=hash_password(password),
            is_admin=is_admin,
            is_active=True,
        )
        s.add(user)
        s.flush()
        s.expunge(user)
    return user
