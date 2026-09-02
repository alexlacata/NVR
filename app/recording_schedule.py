"""Periodically starts/stops each camera's record leg to match its
optional weekly timer (Camera.record_schedule) - see
StreamManager.sync_recording_schedule for the actual start/stop logic.
Checked every minute, comfortably tight for an hourly grid."""
from __future__ import annotations

import asyncio
import logging

from app.ffmpeg_manager import StreamManager
from app.store import CameraStore

logger = logging.getLogger("nvr.recording_schedule")

CHECK_INTERVAL_SECONDS = 60


async def recording_schedule_loop(store: CameraStore, manager: StreamManager, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            manager.sync_recording_schedule(store.list())
        except Exception:  # pragma: no cover - defensive
            logger.exception("recording_schedule: unexpected error in loop")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=CHECK_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass
