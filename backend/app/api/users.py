"""Endpoints de auth y administración de usuarios."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlmodel import Session, select

from app.db import get_session, session_scope
from app.models import Album, User
from app.services import auth as auth_svc

log = logging.getLogger("bbeat.users")

router = APIRouter(tags=["auth"])


def _user_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "is_admin": u.is_admin,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


# ─── Auth ─────────────────────────────────────────────────────


class RegisterIn(BaseModel):
    username: str = Field(min_length=2, max_length=40)
    email: EmailStr
    password: str = Field(min_length=6, max_length=200)


class LoginIn(BaseModel):
    login: str  # username o email
    password: str


class AuthResponse(BaseModel):
    token: str
    user: dict


@router.post("/auth/register", response_model=AuthResponse)
def register(body: RegisterIn) -> dict:
    # Validación de unicidad
    with session_scope() as s:
        existing = s.exec(
            select(User).where(
                (User.username == body.username) | (User.email == body.email.lower())
            )
        ).first()
        if existing:
            raise HTTPException(409, "username o email ya existe")
        first_user = len(s.exec(select(User)).all()) == 0

    user = auth_svc.create_user(
        username=body.username,
        email=body.email,
        password=body.password,
        is_admin=first_user,  # primer usuario es admin automáticamente
    )
    if first_user:
        log.info("primer usuario %s creado como ADMIN", user.username)
        # Asignar álbumes existentes (de antes del multi-user) al admin como públicos
        _assign_orphaned_albums_to(user.id)

    token = auth_svc.create_token(user.id, user.username, user.is_admin)
    return {"token": token, "user": _user_to_dict(user)}


@router.post("/auth/login", response_model=AuthResponse)
def login(body: LoginIn) -> dict:
    user = auth_svc.find_user_by_login(body.login)
    if not user or not auth_svc.verify_password(body.password, user.password_hash):
        raise HTTPException(401, "credenciales inválidas")
    if not user.is_active:
        raise HTTPException(403, "cuenta bloqueada")
    token = auth_svc.create_token(user.id, user.username, user.is_admin)
    return {"token": token, "user": _user_to_dict(user)}


@router.get("/auth/me")
def me(user: User = Depends(auth_svc.get_current_user)) -> dict:
    return _user_to_dict(user)


def _assign_orphaned_albums_to(user_id: int) -> int:
    """Adjudica todos los álbumes sin owner al user dado, como públicos."""
    with session_scope() as s:
        rows = s.exec(select(Album).where(Album.owner_id == None)).all()  # noqa: E711
        for a in rows:
            a.owner_id = user_id
            a.is_public = True
            s.add(a)
        return len(rows)


# ─── Admin ────────────────────────────────────────────────────


admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.get("/users")
def list_users(_: User = Depends(auth_svc.require_admin)) -> dict:
    with session_scope() as s:
        users = s.exec(select(User).order_by(User.created_at)).all()
        return {"total": len(users), "items": [_user_to_dict(u) for u in users]}


class AdminUpdateUser(BaseModel):
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


@admin_router.patch("/users/{user_id}")
def admin_update_user(
    user_id: int,
    body: AdminUpdateUser,
    me: User = Depends(auth_svc.require_admin),
) -> dict:
    if user_id == me.id and body.is_active is False:
        raise HTTPException(400, "no puedes desactivarte a ti mismo")
    with session_scope() as s:
        u = s.get(User, user_id)
        if not u:
            raise HTTPException(404, "usuario no existe")
        if body.is_active is not None:
            u.is_active = body.is_active
        if body.is_admin is not None:
            u.is_admin = body.is_admin
        s.add(u)
        s.flush()
        s.expunge(u)
    return _user_to_dict(u)


@admin_router.delete("/users/{user_id}")
def admin_delete_user(
    user_id: int,
    me: User = Depends(auth_svc.require_admin),
) -> dict:
    if user_id == me.id:
        raise HTTPException(400, "no puedes borrarte a ti mismo")
    with session_scope() as s:
        u = s.get(User, user_id)
        if not u:
            raise HTTPException(404, "usuario no existe")
        s.delete(u)
    return {"ok": True}
