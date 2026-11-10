"""Server-wide runtime settings (editable from the UI, overriding the
NVR_* environment variable defaults for this running instance)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

class RuntimeSettingsUpdate(BaseModel):
    # 0 = no age-based limit ("ecrasement permanent" in the UI): recordings
    # are never deleted just for being old, only once free disk space runs
    # low (see min_free_disk_percent / app.retention.enforce_retention) -
    # the classic continuous-loop DVR behavior. 1-3650 = delete anything
    # older than that many days, same as before this mode existed.
    retention_days: Optional[int] = Field(default=None, ge=0, le=3650)
    min_free_disk_percent: Optional[float] = Field(default=None, ge=0, le=90)
    segment_seconds: Optional[int] = Field(default=None, ge=10, le=3600)
    hls_segment_seconds: Optional[int] = Field(default=None, ge=1, le=30)
    hls_list_size: Optional[int] = Field(default=None, ge=2, le=50)
    thumbnail_interval_seconds: Optional[int] = Field(default=None, ge=5, le=3600)
    thumbnail_check_interval_seconds: Optional[int] = Field(default=None, ge=5, le=600)
    retention_check_interval_seconds: Optional[int] = Field(default=None, ge=10, le=3600)
    motion_check_interval_seconds: Optional[int] = Field(default=None, ge=2, le=300)


class RuntimeSettingsOut(BaseModel):
    retention_days: int
    min_free_disk_percent: float
    segment_seconds: int
    hls_segment_seconds: int
    hls_list_size: int
    thumbnail_interval_seconds: int
    thumbnail_check_interval_seconds: int
    retention_check_interval_seconds: int
    motion_check_interval_seconds: int

