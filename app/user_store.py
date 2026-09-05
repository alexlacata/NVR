"""Persistence for user accounts (YAML file on disk)."""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from passlib.context import CryptContext

from app.models import User, UserCreate, UserRole, UserUpdate

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserNotFound(KeyError):
    pass


class DuplicateUsername(ValueError):
    pass


class LastAdminError(ValueError):
    """Raised when an operation would leave the system with no admin account."""


class UserStore:
    """Thread-safe CRUD store for user accounts, persisted as YAML."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.RLock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write({})

    def _read(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}
        with self._path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data.get("users", {})

    def _write(self, users: dict[str, dict]) -> None:
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
            merged = User(**users[key]).model_copy(update={"totp_secret": secret, "totp_enabled": enabled})
            users[key] = merged.model_dump(mode="json")
            self._write(users)
            return merged

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
