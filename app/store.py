"""Persistence for camera configuration (YAML file on disk)."""
from __future__ import annotations

import re
import threading
import uuid
from pathlib import Path
from typing import Optional

import yaml

from app.models import Camera, CameraCreate, CameraUpdate

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    return slug or uuid.uuid4().hex[:8]


class CameraNotFound(KeyError):
    pass


class DuplicateCameraId(ValueError):
    pass


class CameraStore:
    """Thread-safe CRUD store for cameras, persisted as YAML."""

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
        return data.get("cameras", {})

    def _write(self, cameras: dict[str, dict]) -> None:
        tmp_path = self._path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump({"cameras": cameras}, fh, sort_keys=True, allow_unicode=True)
        tmp_path.replace(self._path)

    def list(self) -> list[Camera]:
        with self._lock:
            cameras = self._read()
            return [Camera(**c) for c in cameras.values()]

    def get(self, camera_id: str) -> Camera:
        with self._lock:
            cameras = self._read()
            if camera_id not in cameras:
                raise CameraNotFound(camera_id)
            return Camera(**cameras[camera_id])

    def try_get(self, camera_id: str) -> Optional[Camera]:
        try:
            return self.get(camera_id)
        except CameraNotFound:
            return None

    def create(self, payload: CameraCreate) -> Camera:
        with self._lock:
            cameras = self._read()
            camera_id = payload.id or slugify(payload.name)
            base_id = camera_id
            suffix = 1
            while camera_id in cameras:
                suffix += 1
                camera_id = f"{base_id}-{suffix}"
            if payload.id and payload.id in cameras:
                raise DuplicateCameraId(payload.id)
            camera = Camera(id=camera_id, **payload.model_dump(exclude={"id"}))
            cameras[camera_id] = camera.model_dump(mode="json")
            self._write(cameras)
            return camera

    def update(self, camera_id: str, payload: CameraUpdate) -> Camera:
        with self._lock:
            cameras = self._read()
            if camera_id not in cameras:
                raise CameraNotFound(camera_id)
            existing = Camera(**cameras[camera_id])
            updates = payload.model_dump(exclude_unset=True)
            merged = existing.model_copy(update=updates)
            # re-validate url/source_type combination
            merged = Camera(**merged.model_dump())
            cameras[camera_id] = merged.model_dump(mode="json")
            self._write(cameras)
            return merged

    def delete(self, camera_id: str) -> None:
        with self._lock:
            cameras = self._read()
            if camera_id not in cameras:
                raise CameraNotFound(camera_id)
            del cameras[camera_id]
            self._write(cameras)
