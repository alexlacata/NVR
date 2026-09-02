"""Admin-only user account management."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_user_store, require_admin
from app.models import User, UserCreate, UserPublic, UserUpdate
from app.user_store import DuplicateUsername, LastAdminError, UserNotFound, UserStore

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


def _public(u: User) -> UserPublic:
    return UserPublic(username=u.username, role=u.role, permissions=u.permissions, created_at=u.created_at)


@router.get("", response_model=list[UserPublic])
def list_users(users: UserStore = Depends(get_user_store)):
    return [_public(u) for u in users.list()]


@router.post("", response_model=UserPublic, status_code=201)
def create_user(payload: UserCreate, users: UserStore = Depends(get_user_store)):
    try:
        user = users.create(payload)
    except DuplicateUsername:
        raise HTTPException(status_code=409, detail="Ce nom d'utilisateur existe deja")
    return _public(user)


@router.patch("/{username}", response_model=UserPublic)
def update_user(
    username: str,
    payload: UserUpdate,
    users: UserStore = Depends(get_user_store),
):
    try:
        user = users.update(username, payload)
    except UserNotFound:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    except LastAdminError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _public(user)


@router.delete("/{username}", status_code=204)
def delete_user(
    username: str,
    current: User = Depends(require_admin),
    users: UserStore = Depends(get_user_store),
):
    if username.strip().lower() == current.username.strip().lower():
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas supprimer votre propre compte")
    try:
        users.delete(username)
    except UserNotFound:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    except LastAdminError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return None
