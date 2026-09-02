from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.auth import COOKIE_NAME, AuthService
from app.config import Settings
from app.deps import get_auth_service, get_settings, get_user_store, require_auth
from app.models import PasswordChange, User, effective_permissions
from app.user_store import UserStore, pwd_context

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    ok: bool
    token: str


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
):
    user = auth_service.verify_credentials(payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Identifiants incorrects")
    token = auth_service.create_token(user.username)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.session_max_age_seconds,
        path="/",
    )
    # Token is also returned in the body so non-browser/API clients (e.g. a
    # native mobile app) can use it as a Bearer token instead of cookies.
    return LoginResponse(ok=True, token=token)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(require_auth)):
    return {
        "username": user.username,
        "role": user.role,
        "permissions": sorted(p.value for p in effective_permissions(user)),
    }


@router.patch("/password")
def change_own_password(
    payload: PasswordChange,
    user: User = Depends(require_auth),
    users: UserStore = Depends(get_user_store),
):
    if not pwd_context.verify(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Mot de passe actuel incorrect")
    users.set_password_hash(user.username, pwd_context.hash(payload.new_password))
    return {"ok": True}
