"""Minimal username/password auth: a signed, expiring session token stored
in an httpOnly cookie (for the web UI) or sent as a Bearer token (for API
clients such as a native mobile app)."""
from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext

from app.config import Settings

COOKIE_NAME = "nvr_session"
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._serializer = URLSafeTimedSerializer(settings.resolve_secret_key(), salt="nvr-session")
        self._password_hash = _pwd_context.hash(settings.admin_password)

    def verify_credentials(self, username: str, password: str) -> bool:
        if username != self._settings.admin_username:
            # still run a hash comparison to reduce timing side-channels
            _pwd_context.verify(password, self._password_hash)
            return False
        return _pwd_context.verify(password, self._password_hash)

    def create_token(self, username: str) -> str:
        return self._serializer.dumps({"sub": username})

    def verify_token(self, token: str) -> bool:
        try:
            data = self._serializer.loads(token, max_age=self._settings.session_max_age_seconds)
        except (BadSignature, SignatureExpired):
            return False
        return data.get("sub") == self._settings.admin_username
