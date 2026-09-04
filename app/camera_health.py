"""Watches each enabled camera's live-leg state and fires an alert once a
camera has been continuously in "error" for camera_offline_after_seconds -
a brief reconnect blip (a few seconds) is normal ffmpeg behavior and
shouldn't page anyone - and again once it recovers."""
from __future__ import annotations

import asyncio
import logging
import time

from app.config import Settings
from app.ffmpeg_manager import StreamManager
from app.notifier import Notifier
from app.store import CameraStore

logger = logging.getLogger("nvr.camera_health")


class CameraHealthRegistry:
    def __init__(self) -> None:
        self._error_since: dict[str, float] = {}
        self._offline_notified: set[str] = set()

    def observe(self, camera_id: str, state: str, offline_after_seconds: float) -> tuple[bool, bool]:
        """Returns (went_offline, came_back_online) edge signals."""
        now = time.monotonic()
        went_offline = False
        came_back_online = False
        if state == "error":
            since = self._error_since.setdefault(camera_id, now)
            if camera_id not in self._offline_notified and now - since >= offline_after_seconds:
                self._offline_notified.add(camera_id)
                went_offline = True
        else:
            self._error_since.pop(camera_id, None)
            if camera_id in self._offline_notified and state == "running":
                self._offline_notified.discard(camera_id)
                came_back_online = True
        return went_offline, came_back_online


async def camera_health_loop(
    settings: Settings,
    store: CameraStore,
    stream_manager: StreamManager,
    notifier: Notifier,
    registry: CameraHealthRegistry,
    stop_event: asyncio.Event,
) -> None:
    while not stop_event.is_set():
        try:
            for camera in store.list():
                if not camera.enabled:
                    continue
                status = stream_manager.status(camera.id)
                went_offline, came_back_online = registry.observe(
                    camera.id, status.state, settings.camera_offline_after_seconds
                )
                if went_offline:
                    await notifier.notify_camera_offline(camera.id, camera.name)
                elif came_back_online:
                    await notifier.notify_camera_online(camera.id, camera.name)
        except Exception:  # pragma: no cover - defensive
            logger.exception("camera_health: unexpected error in loop")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.camera_health_check_interval_seconds)
        except asyncio.TimeoutError:
            pass
