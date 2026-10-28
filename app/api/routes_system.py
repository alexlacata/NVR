from __future__ import annotations

import shutil
from typing import Optional

from fastapi import APIRouter, Depends

from app.config import Settings
from app.deps import get_hw_encoder, get_settings, require_auth
from app.hw_encoder import HW_ENCODER_NAME
from app.system_health import read_system_health

router = APIRouter(prefix="/api/system", tags=["system"], dependencies=[Depends(require_auth)])


@router.get("")
def system_info(
    settings: Settings = Depends(get_settings),
    hw_encoder: Optional[str] = Depends(get_hw_encoder),
):
    usage = shutil.disk_usage(settings.data_dir)
    return {
        "disk_total_bytes": usage.total,
        "disk_used_bytes": usage.used,
        "disk_free_bytes": usage.free,
        "disk_free_percent": round(100.0 * usage.free / usage.total, 1) if usage.total else 0,
        "retention_days": settings.retention_days,
        "min_free_disk_percent": settings.min_free_disk_percent,
        "data_dir": str(settings.data_dir),
        "segment_seconds": settings.segment_seconds,
        "thumbnail_interval_seconds": settings.thumbnail_interval_seconds,
        "video_encoder": "hardware" if hw_encoder == HW_ENCODER_NAME else "software",
        **read_system_health(),
    }
