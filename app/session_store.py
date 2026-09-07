"""Tracks issued login sessions (one entry per token, keyed by a random
session id embedded in the token itself) so a user can see what's logged
in as them and revoke a specific session (lost phone, shared computer)
without changing their password - and so logging out actually
invalidates that token server-side instead of just clearing a cookie the
token itself remains valid without.

Persisted as YAML, same pattern as every other *_store in this app - but
usable with no path (in-memory only) for tests/callers that don't care
about revocation or persistence across a restart."""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml


class SessionStore:
    def __init__(self, path: Optional[Path] = None):
        self._path = path
        self._lock = threading.RLock()
        self._memory: dict[str, dict] = {}
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, dict]:
        if self._path is None:
            return self._memory
        if not self._path.exists():
            return {}
        with self._path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    def _write(self, sessions: dict[str, dict]) -> None:
        if self._path is None:
            self._memory = sessions
            return
        tmp_path = self._path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(sessions, fh, sort_keys=True, allow_unicode=True)
        tmp_path.replace(self._path)

    @staticmethod
    def _key(username: str) -> str:
        return username.strip().lower()

    def record(self, jti: str, username: str, user_agent: str, ip: str) -> None:
        with self._lock:
            sessions = self._read()
            sessions[jti] = {
                "username": username,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "user_agent": user_agent or "",
                "ip": ip or "",
            }
            self._write(sessions)

    def exists(self, jti: str) -> bool:
        with self._lock:
            return jti in self._read()

    def list_for_user(self, username: str, max_age_seconds: Optional[float] = None) -> list[dict]:
        with self._lock:
            sessions = self._read()
            if max_age_seconds is not None:
                pruned = self._without_expired(sessions, max_age_seconds)
                if len(pruned) != len(sessions):
                    self._write(pruned)
                sessions = pruned
            key = self._key(username)
            out = [
                {"jti": jti, **entry}
                for jti, entry in sessions.items()
                if self._key(entry.get("username", "")) == key
            ]
            out.sort(key=lambda e: e["created_at"], reverse=True)
            return out

    def revoke(self, jti: str) -> bool:
        with self._lock:
            sessions = self._read()
            if jti not in sessions:
                return False
            del sessions[jti]
            self._write(sessions)
            return True

    def revoke_all_for_user(self, username: str, except_jti: Optional[str] = None) -> int:
        with self._lock:
            sessions = self._read()
            key = self._key(username)
            to_remove = [
                jti for jti, entry in sessions.items()
                if self._key(entry.get("username", "")) == key and jti != except_jti
            ]
            for jti in to_remove:
                del sessions[jti]
            if to_remove:
                self._write(sessions)
            return len(to_remove)

    @staticmethod
    def _without_expired(sessions: dict[str, dict], max_age_seconds: float) -> dict[str, dict]:
        now = datetime.now(timezone.utc)
        kept = {}
        for jti, entry in sessions.items():
            try:
                created = datetime.fromisoformat(entry["created_at"])
            except (KeyError, ValueError):
                continue
            if (now - created).total_seconds() <= max_age_seconds:
                kept[jti] = entry
        return kept

    def prune_expired(self, max_age_seconds: float) -> None:
        with self._lock:
            sessions = self._read()
            kept = self._without_expired(sessions, max_age_seconds)
            if len(kept) != len(sessions):
                self._write(kept)
