"""Caches one OnvifPTZClient per camera (holding its discovered ONVIF
service addresses and profile token) so PTZ commands don't re-run
discovery on every move."""
from __future__ import annotations

import asyncio

from app.models import Camera
from app.onvif_client import OnvifPTZClient


class PTZRegistry:
    def __init__(self):
        self._clients: dict[str, OnvifPTZClient] = {}
        self._lock = asyncio.Lock()

    async def get(self, camera: Camera) -> OnvifPTZClient:
        async with self._lock:
            existing = self._clients.get(camera.id)
            if existing and existing.matches(camera.onvif_url or "", camera.onvif_username or "", camera.onvif_password or ""):
                return existing
            client = OnvifPTZClient(camera.onvif_url or "", camera.onvif_username or "", camera.onvif_password or "")
            self._clients[camera.id] = client
            return client

    def invalidate(self, camera_id: str) -> None:
        self._clients.pop(camera_id, None)
