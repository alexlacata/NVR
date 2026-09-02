"""Admin-only server configuration - retention, disk threshold, segment
and thumbnail intervals - editable from the web UI and persisted across
restarts (see app.settings_store)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings
from app.deps import get_settings, get_settings_store, get_store, get_stream_manager, require_admin
from app.ffmpeg_manager import StreamManager
from app.models import RuntimeSettingsOut, RuntimeSettingsUpdate
from app.settings_store import SettingsStore
from app.store import CameraStore

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_admin)])


def _out(settings: Settings) -> RuntimeSettingsOut:
    return RuntimeSettingsOut(
        retention_days=settings.retention_days,
        min_free_disk_percent=settings.min_free_disk_percent,
        segment_seconds=settings.segment_seconds,
        hls_segment_seconds=settings.hls_segment_seconds,
        hls_list_size=settings.hls_list_size,
        thumbnail_interval_seconds=settings.thumbnail_interval_seconds,
        thumbnail_check_interval_seconds=settings.thumbnail_check_interval_seconds,
        retention_check_interval_seconds=settings.retention_check_interval_seconds,
    )


@router.get("", response_model=RuntimeSettingsOut)
def get_runtime_settings(settings: Settings = Depends(get_settings)):
    return _out(settings)


@router.patch("", response_model=RuntimeSettingsOut)
async def update_runtime_settings(
    payload: RuntimeSettingsUpdate,
    settings: Settings = Depends(get_settings),
    settings_store: SettingsStore = Depends(get_settings_store),
    store: CameraStore = Depends(get_store),
    manager: StreamManager = Depends(get_stream_manager),
):
    settings_store.update(settings, payload.model_dump(exclude_unset=True))
    # Segment/HLS/thumbnail intervals only take effect for ffmpeg legs
    # started after the change, so restart every camera's legs now rather
    # than leaving already-running streams on the old values.
    await manager.restart_all(store.list())
    return _out(settings)
