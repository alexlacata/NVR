from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth import COOKIE_NAME, AuthService
from app.config import Settings
from app.deps import (
    get_auth_service,
    get_current_jti,
    get_login_throttle,
    get_session_store,
    get_settings,
    get_user_store,
    require_auth,
)
from app.login_throttle import LoginThrottle
from app.models import PasswordChange, User, effective_permissions
from app.session_store import SessionStore
from app.totp import generate_recovery_codes, generate_secret, provisioning_uri, verify_totp
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


class TotpConfirmResponse(BaseModel):
    ok: bool
    recovery_codes: list[str]


class RecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


class RegenerateRecoveryCodesRequest(BaseModel):
    password: str


class SessionOut(BaseModel):
    jti: str
    created_at: str
    user_agent: str
    ip: str
    current: bool


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
    throttle: LoginThrottle = Depends(get_login_throttle),
    users: UserStore = Depends(get_user_store),
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
        # A code that isn't a valid TOTP right now might still be a
        # recovery code (format "XXXX-XXXX" vs. 6 digits) - try that before
        # failing, since losing the authenticator app is exactly the case
        # recovery codes exist for.
        if not verify_totp(user.totp_secret, payload.totp_code) and not users.try_consume_recovery_code(
            user.username, payload.totp_code.strip()
        ):
            throttle.record_failure(payload.username)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Code de verification incorrect")
    throttle.record_success(payload.username)
    token = auth_service.create_token(
        user.username,
        user_agent=request.headers.get("user-agent", ""),
        ip=(request.client.host if request.client else ""),
    )
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
def logout(
    response: Response,
    current_jti: Optional[str] = Depends(get_current_jti),
    sessions: SessionStore = Depends(get_session_store),
):
    # Revoked server-side, not just the cookie cleared - otherwise a copy
    # of the token taken before logout (a proxy log, a shared computer's
    # browser history) would stay valid until it naturally expires.
    if current_jti:
        sessions.revoke(current_jti)
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(require_auth)):
    return {
        "username": user.username,
        "role": user.role,
        "permissions": sorted(p.value for p in effective_permissions(user)),
        "totp_enabled": user.totp_enabled,
        "totp_recovery_codes_remaining": len(user.totp_recovery_codes),
    }


@router.patch("/password")
def change_own_password(
    payload: PasswordChange,
    user: User = Depends(require_auth),
    users: UserStore = Depends(get_user_store),
    sessions: SessionStore = Depends(get_session_store),
    current_jti: Optional[str] = Depends(get_current_jti),
):
    if not pwd_context.verify(payload.current_password, user.password_hash):
        # 403, not 401: the session itself is valid (require_auth already
        # passed) - only the submitted current-password check failed. The
        # frontend's generic api() helper treats any 401 as "session
        # expired" and redirects straight to the login page, which would
        # silently wipe this error out instead of showing it in the form.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Mot de passe actuel incorrect")
    users.set_password_hash(user.username, pwd_context.hash(payload.new_password))
    # A changed password is often a reaction to a suspected compromise -
    # kick out every other session (a stolen cookie, a forgotten shared
    # computer) rather than leaving them valid until they expire on their
    # own. The session making this very request stays logged in.
    sessions.revoke_all_for_user(user.username, except_jti=current_jti)
    return {"ok": True}


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    user: User = Depends(require_auth),
    current_jti: Optional[str] = Depends(get_current_jti),
    sessions: SessionStore = Depends(get_session_store),
    settings: Settings = Depends(get_settings),
):
    entries = sessions.list_for_user(user.username, max_age_seconds=settings.session_max_age_seconds)
    return [
        SessionOut(
            jti=e["jti"], created_at=e["created_at"], user_agent=e["user_agent"], ip=e["ip"],
            current=(e["jti"] == current_jti),
        )
        for e in entries
    ]


@router.delete("/sessions/{jti}")
def revoke_session(
    jti: str,
    user: User = Depends(require_auth),
    sessions: SessionStore = Depends(get_session_store),
):
    owned = any(e["jti"] == jti for e in sessions.list_for_user(user.username))
    if not owned:
        raise HTTPException(status_code=404, detail="Session introuvable")
    sessions.revoke(jti)
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


@router.post("/totp/confirm", response_model=TotpConfirmResponse)
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
    codes = generate_recovery_codes()
    users.set_totp_recovery_codes(user.username, [pwd_context.hash(c) for c in codes])
    return TotpConfirmResponse(ok=True, recovery_codes=codes)


@router.post("/totp/recovery-codes/regenerate", response_model=RecoveryCodesResponse)
def regenerate_recovery_codes(
    payload: RegenerateRecoveryCodesRequest,
    user: User = Depends(require_auth),
    users: UserStore = Depends(get_user_store),
):
    """Invalidates all existing recovery codes and issues a fresh set -
    for after using one, or if you suspect the old ones leaked. Requires
    the current password since, like disabling 2FA, this changes what can
    get into the account."""
    if not pwd_context.verify(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Mot de passe incorrect")
    fresh = users.get(user.username)
    if not fresh.totp_enabled:
        raise HTTPException(status_code=400, detail="La double authentification n'est pas activee")
    codes = generate_recovery_codes()
    users.set_totp_recovery_codes(user.username, [pwd_context.hash(c) for c in codes])
    return RecoveryCodesResponse(recovery_codes=codes)


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
