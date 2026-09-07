"""Generic per-identity request-rate limiter, extending the login
endpoint's anti-bruteforce throttling (see login_throttle.py) to the rest
of the API: a fixed-window counter keyed by the caller's identity, so no
single account (or client IP, before login) can hammer any endpoint.
Same in-memory, single-process tradeoff as LoginThrottle - a restart
clearing the counters is acceptable for a self-hosted app."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

# Above this many distinct identities tracked at once, opportunistically
# drop entries whose window has already elapsed - keeps memory bounded
# under sustained scanning/bot traffic from many IPs without needing a
# background sweep task.
_PRUNE_THRESHOLD = 10_000


@dataclass
class _Window:
    count: int = 0
    started_at: float = 0.0


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: float):
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._windows: dict[str, _Window] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, float]:
        """Call once per request for the identity making it. Returns
        (allowed, retry_after_seconds) - retry_after is 0 when allowed."""
        now = time.monotonic()
        with self._lock:
            if len(self._windows) > _PRUNE_THRESHOLD:
                self._prune(now)
            window = self._windows.get(key)
            if window is None or now - window.started_at >= self._window_seconds:
                window = _Window(count=0, started_at=now)
                self._windows[key] = window
            window.count += 1
            if window.count > self._max_requests:
                retry_after = self._window_seconds - (now - window.started_at)
                return False, max(0.0, retry_after)
            return True, 0.0

    def _prune(self, now: float) -> None:
        expired = [k for k, w in self._windows.items() if now - w.started_at >= self._window_seconds]
        for k in expired:
            del self._windows[k]
