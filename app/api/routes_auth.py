from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth import COOKIE_NAME, AuthService
from app.config import Settings
from app.deps import get_auth_service, get_login_throttle, get_settings, get_user_store, require_auth
from app.login_throttle import LoginThrottle
from app.models import PasswordChange, User, effective_permissions
from app.totp import generate_secret, provisioning_uri, verify_totp
from app.user_store import UserStore, pwd_context

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str
    totp_code: Optional[str] = None


class LoginResponse(BaseModel):
    ok: bool
    token: str


class TotpEnrollResponse(BaseModel):
    secret: str
    otpauth_uri: str


class TotpConfirmRequest(BaseModel):
    code: str


class TotpDisableRequest(BaseModel):
    password: str


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
    if user.totp_enabled:
        if not payload.totp_code:
            # Not a failed attempt (the password was correct) - don't count
            # it against the lockout, just prompt the client for the second
            # factor. `totp_required` lets the frontend switch to a code
            # field without having to parse the message text.
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Code de verification a deux facteurs requis", "totp_required": True},
            )
        if not verify_totp(user.totp_secret, payload.totp_code):
            throttle.record_failure(payload.username)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Code de verification incorrect")
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
        "totp_enabled": user.totp_enabled,
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


@router.post("/totp/enroll", response_model=TotpEnrollResponse)
def enroll_totp(user: User = Depends(require_auth), users: UserStore = Depends(get_user_store)):
    """Starts (or restarts) 2FA enrollment: generates a new secret and
    returns it plus a QR-encodable otpauth:// URI. Not yet active -
    totp_enabled only flips to True via /totp/confirm, once the caller
    proves they can generate a matching code."""
    secret = generate_secret()
    users.set_totp(user.username, secret=secret, enabled=False)
    return TotpEnrollResponse(secret=secret, otpauth_uri=provisioning_uri(secret, user.username))


@router.post("/totp/confirm")
def confirm_totp(
    payload: TotpConfirmRequest,
    user: User = Depends(require_auth),
    users: UserStore = Depends(get_user_store),
):
    fresh = users.get(user.username)
    if not fresh.totp_secret:
        raise HTTPException(status_code=400, detail="Aucun enrolement 2FA en cours - relancez depuis Parametres")
    if not verify_totp(fresh.totp_secret, payload.code):
        raise HTTPException(status_code=400, detail="Code incorrect")
    users.set_totp(user.username, secret=fresh.totp_secret, enabled=True)
    return {"ok": True}


@router.post("/totp/disable")
def disable_totp(
    payload: TotpDisableRequest,
    user: User = Depends(require_auth),
    users: UserStore = Depends(get_user_store),
):
    if not pwd_context.verify(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Mot de passe incorrect")
    users.set_totp(user.username, secret=None, enabled=False)
    return {"ok": True}
