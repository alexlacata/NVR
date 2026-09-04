"""In-memory anti-bruteforce guard for the login endpoint: after too many
failed attempts for a given username in a short window, further attempts
for that username are rejected for a cooldown period. Deliberately
per-username rather than per-IP - viewers on 4G/CGNAT or behind a shared
router can share an IP, and locking by IP would lock out everyone behind
it; locking the targeted account is the actual bruteforce-relevant
boundary. In-memory (not persisted) is fine here: this is a single-process
app, and a restart clearing the counters is an acceptable tradeoff."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class _Entry:
    fail_count: int = 0
    first_fail_at: float = 0.0
    locked_until: float = 0.0


class LoginThrottle:
    def __init__(self, max_attempts: int, window_seconds: float, lockout_seconds: float):
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._lockout_seconds = lockout_seconds
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def _key(self, username: str) -> str:
        return username.strip().lower()

    def seconds_until_unlocked(self, username: str) -> float:
        """0 if the account can attempt a login right now, else the number
        of seconds left before it can."""
        with self._lock:
            entry = self._entries.get(self._key(username))
            if entry is None:
                return 0.0
            remaining = entry.locked_until - time.monotonic()
            return max(0.0, remaining)

    def record_failure(self, username: str) -> None:
        key = self._key(username)
        now = time.monotonic()
        with self._lock:
            entry = self._entries.setdefault(key, _Entry())
            if now - entry.first_fail_at > self._window_seconds:
                entry.fail_count = 0
                entry.first_fail_at = now
            entry.fail_count += 1
            if entry.fail_count >= self._max_attempts:
                entry.locked_until = now + self._lockout_seconds

    def record_success(self, username: str) -> None:
        with self._lock:
            self._entries.pop(self._key(username), None)
