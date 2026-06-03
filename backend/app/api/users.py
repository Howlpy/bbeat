"""Endpoints de auth y administración de usuarios."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlmodel import Session, select

from app.db import get_session, session_scope
from app.models import Album, AlbumSave, User
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
        "is_approved": u.is_approved,
        "subsonic_token": u.subsonic_token,
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


@router.post("/auth/register")
def register(body: RegisterIn) -> dict:
    # Validación de unicidad (case-insensitive en username)
    with session_scope() as s:
        existing = s.exec(
            select(User).where(
                (func.lower(User.username) == body.username.strip().lower())
                | (User.email == body.email.lower())
            )
        ).first()
        if existing:
            raise HTTPException(409, "username o email ya existe")
        first_user = len(s.exec(select(User)).all()) == 0

    # El primer usuario es admin y entra aprobado; el resto quedan PENDIENTES
    # de que un admin los apruebe en /admin.
    user = auth_svc.create_user(
        username=body.username,
        email=body.email,
        password=body.password,
        is_admin=first_user,
        is_approved=first_user,
    )
    if first_user:
        log.info("primer usuario %s creado como ADMIN", user.username)
        _assign_orphaned_albums_to(user.id)
        token = auth_svc.create_token(user.id, user.username, user.is_admin)
        return {"token": token, "user": _user_to_dict(user)}

    log.info("registro pendiente de aprobación: %s", user.username)
    return {"pending": True, "user": _user_to_dict(user)}


@router.post("/auth/login", response_model=AuthResponse)
def login(body: LoginIn) -> dict:
    user = auth_svc.find_user_by_login(body.login)
    if not user or not auth_svc.verify_password(body.password, user.password_hash):
        raise HTTPException(401, "credenciales inválidas")
    if not user.is_active:
        raise HTTPException(403, "cuenta bloqueada")
    if not user.is_approved:
        raise HTTPException(403, "tu cuenta está pendiente de aprobación por el administrador")
    token = auth_svc.create_token(user.id, user.username, user.is_admin)
    return {"token": token, "user": _user_to_dict(user)}


@router.get("/auth/me")
def me(user: User = Depends(auth_svc.get_current_user)) -> dict:
    return _user_to_dict(user)


# ─── Token de acceso Subsonic ─────────────────────────────────
# Secreto dedicado para clientes Subsonic (iPhone y demás). No reutilizamos el
# password porque es bcrypt (irreversible) y el protocolo exige poder recomputar
# md5(token+salt) o validar el password en claro.


@router.post("/auth/subsonic-token")
def generate_subsonic_token(
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Genera (o regenera) el token Subsonic del usuario y lo devuelve."""
    import secrets

    db_user = session.get(User, user.id)
    db_user.subsonic_token = secrets.token_urlsafe(24)
    session.add(db_user)
    return {"subsonic_token": db_user.subsonic_token}


@router.delete("/auth/subsonic-token")
def revoke_subsonic_token(
    user: User = Depends(auth_svc.get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Revoca el token Subsonic (los clientes dejan de poder conectarse)."""
    db_user = session.get(User, user.id)
    db_user.subsonic_token = None
    session.add(db_user)
    return {"subsonic_token": None}


def _assign_orphaned_albums_to(user_id: int) -> int:
    """Adjudica todos los álbumes sin owner al user dado y se los guarda."""
    with session_scope() as s:
        rows = s.exec(select(Album).where(Album.owner_id == None)).all()  # noqa: E711
        for a in rows:
            a.owner_id = user_id
            s.add(a)
            if not s.get(AlbumSave, (user_id, a.id)):
                s.add(AlbumSave(user_id=user_id, album_id=a.id))
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
    is_approved: Optional[bool] = None


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
        if body.is_approved is not None:
            u.is_approved = body.is_approved
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
