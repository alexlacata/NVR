"""Persists notification (webhook/email) settings as YAML - a single
record, unlike the list-shaped stores (cameras, users, systems)."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

import yaml

from app.models import NotificationSettings
from app.secrets_crypto import SecretsCipher

FIELDS = tuple(NotificationSettings.model_fields.keys())


class NotificationSettingsStore:
    def __init__(self, path: Path, cipher: Optional[SecretsCipher] = None):
        self._path = path
        # Encrypts smtp_password at rest when a cipher is provided; None
        # (the default) keeps prior behavior for callers/tests that don't
        # care about it, storing it in plaintext as before.
        self._cipher = cipher
        self._lock = threading.RLock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def get(self) -> NotificationSettings:
        with self._lock:
            if not self._path.exists():
                return NotificationSettings()
            with self._path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            fields = {k: v for k, v in data.items() if k in FIELDS}
            if self._cipher and fields.get("smtp_password"):
                fields["smtp_password"] = self._cipher.decrypt(fields["smtp_password"])
            return NotificationSettings(**fields)

    def update(self, patch: dict) -> NotificationSettings:
        with self._lock:
            current = self.get().model_dump()
            for key, value in patch.items():
                if key in FIELDS and value is not None:
                    current[key] = value
            updated = NotificationSettings(**current)
            to_persist = updated.model_dump()
            if self._cipher and to_persist.get("smtp_password"):
                to_persist["smtp_password"] = self._cipher.encrypt(to_persist["smtp_password"])
            tmp_path = self._path.with_suffix(".tmp")
            with tmp_path.open("w", encoding="utf-8") as fh:
                yaml.safe_dump(to_persist, fh, sort_keys=True)
            tmp_path.replace(self._path)
            return updated
