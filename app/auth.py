"""Multi-user username/password auth: a signed, expiring session token
stored in an httpOnly cookie (for the web UI) or sent as a Bearer token
(for API clients such as a native mobile app). Accounts and roles are
managed via UserStore; see bootstrap_admin() for first-run setup."""
from __future__ import annotations

import secrets
from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import Settings
from app.models import User, UserCreate, UserRole
from app.session_store import SessionStore
from app.user_store import UserStore, pwd_context

COOKIE_NAME = "nvr_session"

# A pre-computed hash checked when the username doesn't exist, so a
# wrong-username attempt takes the same time as a wrong-password one.
_DUMMY_HASH = pwd_context.hash("not-a-real-password-used-only-for-timing")


def bootstrap_admin(settings: Settings, users: UserStore) -> None:
    """On a fresh install (no accounts yet), create the initial admin
    account from NVR_ADMIN_USERNAME/NVR_ADMIN_PASSWORD. Manage accounts
    from the web UI afterwards - these env vars have no further effect
    once at least one account exists."""
    if not users.is_empty():
        return
    users.create(UserCreate(
        username=settings.admin_username,
        password=settings.admin_password,
        role=UserRole.admin,
    ))


class AuthService:
    def __init__(self, settings: Settings, users: UserStore, sessions: Optional[SessionStore] = None):
        self._settings = settings
        self._users = users
        # Defaults to an in-memory-only store (no revocation persisted
        # across a restart) so callers that don't care about session
        # management - most existing tests - don't need to wire one up.
        self._sessions = sessions if sessions is not None else SessionStore()
        self._serializer = URLSafeTimedSerializer(settings.resolve_secret_key(), salt="nvr-session")

    def verify_credentials(self, username: str, password: str) -> Optional[User]:
        user = self._users.try_get(username)
        if user is None:
            pwd_context.verify(password, _DUMMY_HASH)
            return None
        if not pwd_context.verify(password, user.password_hash):
            return None
        return user

    def create_token(self, username: str, user_agent: str = "", ip: str = "") -> str:
        jti = secrets.token_hex(16)
        self._sessions.record(jti, username, user_agent, ip)
        return self._serializer.dumps({"sub": username, "jti": jti})

    def _decode(self, token: str) -> Optional[dict]:
        try:
            return self._serializer.loads(token, max_age=self._settings.session_max_age_seconds)
        except (BadSignature, SignatureExpired):
            return None

    def verify_token(self, token: str) -> Optional[User]:
        data = self._decode(token)
        if data is None:
            return None
        # Tokens issued before session tracking existed carry no "jti" -
        # treat those as always valid (until they naturally expire) rather
        # than forcing every existing session to re-login on upgrade.
        jti = data.get("jti")
        if jti and not self._sessions.exists(jti):
            return None
        username = data.get("sub")
        if not username:
            return None
        return self._users.try_get(username)

    def session_id_from_token(self, token: str) -> Optional[str]:
        data = self._decode(token)
        return data.get("jti") if data else None
