"""Multi-user username/password auth: a signed, expiring session token
stored in an httpOnly cookie (for the web UI) or sent as a Bearer token
(for API clients such as a native mobile app). Accounts and roles are
managed via UserStore; see bootstrap_admin() for first-run setup."""
from __future__ import annotations

from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import Settings
from app.models import User, UserCreate, UserRole
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
    def __init__(self, settings: Settings, users: UserStore):
        self._settings = settings
        self._users = users
        self._serializer = URLSafeTimedSerializer(settings.resolve_secret_key(), salt="nvr-session")

    def verify_credentials(self, username: str, password: str) -> Optional[User]:
        user = self._users.try_get(username)
        if user is None:
            pwd_context.verify(password, _DUMMY_HASH)
            return None
        if not pwd_context.verify(password, user.password_hash):
            return None
        return user

    def create_token(self, username: str) -> str:
        return self._serializer.dumps({"sub": username})

    def verify_token(self, token: str) -> Optional[User]:
        try:
            data = self._serializer.loads(token, max_age=self._settings.session_max_age_seconds)
        except (BadSignature, SignatureExpired):
            return None
        username = data.get("sub")
        if not username:
            return None
        return self._users.try_get(username)
