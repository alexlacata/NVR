"""Append-only log of who viewed/downloaded which recording, and when -
chain-of-custody-lite for a NVR that might need to answer "who watched
this footage" after the fact. Deliberately simple (a JSONL file, same
pattern as app.motion's per-camera event log) rather than a database:
this app has no database, and audit volume is low (one line per view/
download, not per API call in general)."""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("nvr.audit")


class AuditLog:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._last_recorded: dict[tuple, float] = {}

    def record(self, username: str, action: str, camera_id: str, filename: str, dedupe_seconds: float = 0) -> None:
        """dedupe_seconds > 0 skips writing a new entry if the same
        (username, action, camera_id, filename) was just recorded - inline
        <video> playback issues many byte-range GETs while seeking a single
        recording, which would otherwise write one "view" line per range
        request instead of one per actual viewing session."""
        key = (username, action, camera_id, filename)
        if dedupe_seconds > 0:
            now = time.monotonic()
            last = self._last_recorded.get(key)
            if last is not None and now - last < dedupe_seconds:
                return
            self._last_recorded[key] = now

        entry = {
            "at": datetime.now(timezone.utc).isoformat(),
            "username": username,
            "action": action,  # "view" | "download"
            "camera_id": camera_id,
            "filename": filename,
        }
        with self._lock:
            try:
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry) + "\n")
            except OSError:
                logger.exception("audit: failed to append entry")

    def recent(self, limit: int = 200) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        entries = []
        for line in lines[-limit:]:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        entries.reverse()  # most recent first
        return entries
