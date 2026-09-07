"""Persistence for user accounts (YAML file on disk)."""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from passlib.context import CryptContext

from app.models import User, UserCreate, UserRole, UserUpdate
from app.secrets_crypto import SecretsCipher

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserNotFound(KeyError):
    pass


class DuplicateUsername(ValueError):
    pass


class LastAdminError(ValueError):
    """Raised when an operation would leave the system with no admin account."""


class UserStore:
    """Thread-safe CRUD store for user accounts, persisted as YAML."""

    def __init__(self, path: Path, cipher: Optional[SecretsCipher] = None):
        self._path = path
        # Encrypts totp_secret at rest when a cipher is provided; every
        # method below reads/writes plain dicts as before - only this
        # read/write boundary knows about encryption, so a missed spot
        # elsewhere in the store can't leave a secret unencrypted.
        self._cipher = cipher
        self._lock = threading.RLock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write({})

    def _read(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}
        with self._path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        users = data.get("users", {})
        if self._cipher:
            for user in users.values():
                if user.get("totp_secret"):
                    user["totp_secret"] = self._cipher.decrypt(user["totp_secret"])
        return users

    def _write(self, users: dict[str, dict]) -> None:
        if self._cipher:
            users = {
                key: {**user, "totp_secret": self._cipher.encrypt(user["totp_secret"])}
                if user.get("totp_secret") else user
                for key, user in users.items()
            }
        tmp_path = self._path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump({"users": users}, fh, sort_keys=True, allow_unicode=True)
        tmp_path.replace(self._path)

    @staticmethod
    def _key(username: str) -> str:
        return username.strip().lower()

    def is_empty(self) -> bool:
        with self._lock:
            return not self._read()

    def list(self) -> list[User]:
        with self._lock:
            return [User(**u) for u in self._read().values()]

    def get(self, username: str) -> User:
        with self._lock:
            users = self._read()
            key = self._key(username)
            if key not in users:
                raise UserNotFound(username)
            return User(**users[key])

    def try_get(self, username: str) -> Optional[User]:
        try:
            return self.get(username)
        except UserNotFound:
            return None

    def count_admins(self) -> int:
        with self._lock:
            return sum(1 for u in self._read().values() if u.get("role") == UserRole.admin.value)

    def create(self, payload: UserCreate) -> User:
        with self._lock:
            users = self._read()
            key = self._key(payload.username)
            if key in users:
                raise DuplicateUsername(payload.username)
            user = User(
                username=payload.username,
                role=payload.role,
                permissions=payload.permissions,
                password_hash=pwd_context.hash(payload.password),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            users[key] = user.model_dump(mode="json")
            self._write(users)
            return user

    def update(self, username: str, payload: UserUpdate) -> User:
        with self._lock:
            users = self._read()
            key = self._key(username)
            if key not in users:
                raise UserNotFound(username)
            existing = User(**users[key])
            if payload.role is not None and payload.role != UserRole.admin and existing.role == UserRole.admin:
                remaining_admins = sum(
                    1 for u in users.values() if u.get("role") == UserRole.admin.value and self._key(u["username"]) != key
                )
                if remaining_admins == 0:
                    raise LastAdminError("Impossible de retirer le dernier compte administrateur")
            updates: dict = {}
            if payload.role is not None:
                updates["role"] = payload.role
            if payload.permissions is not None:
                updates["permissions"] = payload.permissions
            if payload.password is not None:
                updates["password_hash"] = pwd_context.hash(payload.password)
            merged = existing.model_copy(update=updates)
            users[key] = merged.model_dump(mode="json")
            self._write(users)
            return merged

    def set_password_hash(self, username: str, password_hash: str) -> User:
        with self._lock:
            users = self._read()
            key = self._key(username)
            if key not in users:
                raise UserNotFound(username)
            merged = User(**users[key]).model_copy(update={"password_hash": password_hash})
            users[key] = merged.model_dump(mode="json")
            self._write(users)
            return merged

    def set_totp(self, username: str, secret: Optional[str], enabled: bool) -> User:
        with self._lock:
            users = self._read()
            key = self._key(username)
            if key not in users:
                raise UserNotFound(username)
            updates = {"totp_secret": secret, "totp_enabled": enabled}
            if not enabled:
                # Starting a new enrollment or disabling outright both make
                # any previously issued recovery codes meaningless - a code
                # for a 2FA setup that no longer exists shouldn't still work.
                updates["totp_recovery_codes"] = []
            merged = User(**users[key]).model_copy(update=updates)
            users[key] = merged.model_dump(mode="json")
            self._write(users)
            return merged

    def set_totp_recovery_codes(self, username: str, hashed_codes: list[str]) -> User:
        with self._lock:
            users = self._read()
            key = self._key(username)
            if key not in users:
                raise UserNotFound(username)
            merged = User(**users[key]).model_copy(update={"totp_recovery_codes": hashed_codes})
            users[key] = merged.model_dump(mode="json")
            self._write(users)
            return merged

    def try_consume_recovery_code(self, username: str, code: str) -> bool:
        """Checks `code` against the account's remaining hashed recovery
        codes; if one matches, removes it (single-use) and returns True.
        Done under the store's lock so a code can't be raced into being
        used twice concurrently."""
        with self._lock:
            users = self._read()
            key = self._key(username)
            if key not in users:
                return False
            user = User(**users[key])
            for hashed in user.totp_recovery_codes:
                if pwd_context.verify(code, hashed):
                    remaining = [h for h in user.totp_recovery_codes if h != hashed]
                    merged = user.model_copy(update={"totp_recovery_codes": remaining})
                    users[key] = merged.model_dump(mode="json")
                    self._write(users)
                    return True
            return False

    def delete(self, username: str) -> None:
        with self._lock:
            users = self._read()
            key = self._key(username)
            if key not in users:
                raise UserNotFound(username)
            if users[key].get("role") == UserRole.admin.value:
                remaining_admins = sum(
                    1 for k, u in users.items() if u.get("role") == UserRole.admin.value and k != key
                )
                if remaining_admins == 0:
                    raise LastAdminError("Impossible de supprimer le dernier compte administrateur")
            del users[key]
            self._write(users)
