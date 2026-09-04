from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.auth import COOKIE_NAME, AuthService
from app.config import Settings
from app.deps import get_auth_service, get_login_throttle, get_settings, get_user_store, require_auth
from app.login_throttle import LoginThrottle
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
    throttle: LoginThrottle = Depends(get_login_throttle),
):
    wait = throttle.seconds_until_unlocked(payload.username)
    if wait > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Trop de tentatives - reessayez dans {int(wait) + 1} secondes",
            headers={"Retry-After": str(int(wait) + 1)},
        )
    user = auth_service.verify_credentials(payload.username, payload.password)
    if user is None:
        throttle.record_failure(payload.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Identifiants incorrects")
    throttle.record_success(payload.username)
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
        # 403, not 401: the session itself is valid (require_auth already
        # passed) - only the submitted current-password check failed. The
        # frontend's generic api() helper treats any 401 as "session
        # expired" and redirects straight to the login page, which would
        # silently wipe this error out instead of showing it in the form.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Mot de passe actuel incorrect")
    users.set_password_hash(user.username, pwd_context.hash(payload.new_password))
    return {"ok": True}
