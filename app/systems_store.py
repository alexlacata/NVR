"""Persistence for the directory of *other* NVR systems this one links out
to (each a separate installation - own cameras, own accounts, own disk).
Not to be confused with CameraStore, which manages this NVR's own cameras."""
from __future__ import annotations

import threading
from pathlib import Path

import yaml

from app.models import RemoteSystem, RemoteSystemCreate, RemoteSystemUpdate
from app.store import slugify


class RemoteSystemNotFound(KeyError):
    pass


class DuplicateRemoteSystemId(ValueError):
    pass


class RemoteSystemStore:
    """Thread-safe CRUD store for the linked-systems directory, YAML file."""

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
        return data.get("systems", {})

    def _write(self, systems: dict[str, dict]) -> None:
        tmp_path = self._path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump({"systems": systems}, fh, sort_keys=True, allow_unicode=True)
        tmp_path.replace(self._path)

    def list(self) -> list[RemoteSystem]:
        with self._lock:
            systems = self._read()
            return [RemoteSystem(**s) for s in systems.values()]

    def get(self, system_id: str) -> RemoteSystem:
        with self._lock:
            systems = self._read()
            if system_id not in systems:
                raise RemoteSystemNotFound(system_id)
            return RemoteSystem(**systems[system_id])

    def create(self, payload: RemoteSystemCreate) -> RemoteSystem:
        with self._lock:
            systems = self._read()
            system_id = payload.id or slugify(payload.name)
            base_id = system_id
            suffix = 1
            while system_id in systems:
                suffix += 1
                system_id = f"{base_id}-{suffix}"
            if payload.id and payload.id in systems:
                raise DuplicateRemoteSystemId(payload.id)
            system = RemoteSystem(id=system_id, **payload.model_dump(exclude={"id"}))
            systems[system_id] = system.model_dump(mode="json")
            self._write(systems)
            return system

    def update(self, system_id: str, payload: RemoteSystemUpdate) -> RemoteSystem:
        with self._lock:
            systems = self._read()
            if system_id not in systems:
                raise RemoteSystemNotFound(system_id)
            existing = RemoteSystem(**systems[system_id])
            updates = payload.model_dump(exclude_unset=True)
            merged = existing.model_copy(update=updates)
            merged = RemoteSystem(**merged.model_dump())  # re-run validators (e.g. url normalization)
            systems[system_id] = merged.model_dump(mode="json")
            self._write(systems)
            return merged

    def delete(self, system_id: str) -> None:
        with self._lock:
            systems = self._read()
            if system_id not in systems:
                raise RemoteSystemNotFound(system_id)
            del systems[system_id]
            self._write(systems)
