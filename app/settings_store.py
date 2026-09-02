"""Persists admin-editable server settings (YAML), layered on top of the
env-var defaults in app.config.Settings so changes made from the web UI
survive a restart without needing to touch .env."""
from __future__ import annotations

import threading
from pathlib import Path

import yaml

from app.config import Settings

# Only these fields can be changed at runtime from the UI. Everything else
# (data_dir, secret_key, host/port, ffmpeg paths, admin bootstrap creds) is
# either security-sensitive or needs a process restart anyway, so it stays
# env-var-only.
OVERRIDABLE_FIELDS = (
    "retention_days",
    "min_free_disk_percent",
    "segment_seconds",
    "hls_segment_seconds",
    "hls_list_size",
    "thumbnail_interval_seconds",
    "thumbnail_check_interval_seconds",
    "retention_check_interval_seconds",
)


class SettingsStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.RLock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load_overrides(self) -> dict:
        with self._lock:
            if not self._path.exists():
                return {}
            with self._path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            return {k: v for k, v in data.items() if k in OVERRIDABLE_FIELDS}

    def _save_overrides(self, overrides: dict) -> None:
        tmp_path = self._path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(overrides, fh, sort_keys=True)
        tmp_path.replace(self._path)

    def apply_to(self, settings: Settings) -> None:
        """Mutate a live Settings instance in place with any persisted
        overrides. Call once at startup, before anything reads `settings`."""
        for key, value in self.load_overrides().items():
            setattr(settings, key, value)

    def update(self, settings: Settings, patch: dict) -> None:
        """Persist new overrides and apply them to the given Settings
        instance immediately (`patch` values that are None are ignored,
        so a partial update leaves other fields untouched)."""
        with self._lock:
            overrides = self.load_overrides()
            for key, value in patch.items():
                if key not in OVERRIDABLE_FIELDS or value is None:
                    continue
                overrides[key] = value
                setattr(settings, key, value)
            self._save_overrides(overrides)
