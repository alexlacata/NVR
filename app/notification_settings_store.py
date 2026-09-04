"""Persists notification (webhook/email) settings as YAML - a single
record, unlike the list-shaped stores (cameras, users, systems)."""
from __future__ import annotations

import threading
from pathlib import Path

import yaml

from app.models import NotificationSettings

FIELDS = tuple(NotificationSettings.model_fields.keys())


class NotificationSettingsStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.RLock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def get(self) -> NotificationSettings:
        with self._lock:
            if not self._path.exists():
                return NotificationSettings()
            with self._path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            return NotificationSettings(**{k: v for k, v in data.items() if k in FIELDS})

    def update(self, patch: dict) -> NotificationSettings:
        with self._lock:
            current = self.get().model_dump()
            for key, value in patch.items():
                if key in FIELDS and value is not None:
                    current[key] = value
            updated = NotificationSettings(**current)
            tmp_path = self._path.with_suffix(".tmp")
            with tmp_path.open("w", encoding="utf-8") as fh:
                yaml.safe_dump(updated.model_dump(), fh, sort_keys=True)
            tmp_path.replace(self._path)
            return updated
