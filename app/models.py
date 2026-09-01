"""Data models for cameras."""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-_]{1,63}$")


class SourceType(str, Enum):
    rtsp = "rtsp"       # rtsp://... IP camera
    http = "http"       # http(s):// MJPEG/HTTP video stream
    usb = "usb"         # local capture device, e.g. /dev/video0
    test = "test"       # synthetic test pattern, useful to validate the pipeline
                          # without an actual camera attached


class CameraBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    source_type: SourceType = SourceType.rtsp
    url: str = Field(min_length=1, max_length=2000)
    # Optional lower-resolution "sub stream" URL used only for the live view,
    # while `url` (main stream) is used for recording. Leave empty to reuse
    # `url` for both. Only meaningful for rtsp/http sources.
    live_url: Optional[str] = Field(default=None, max_length=2000)
    enabled: bool = True
    record: bool = True

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str, info) -> str:
        source_type = info.data.get("source_type")
        v = v.strip()
        if source_type == SourceType.rtsp and not v.startswith("rtsp://"):
            raise ValueError("L'URL d'une camera RTSP doit commencer par rtsp://")
        if source_type == SourceType.http and not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("L'URL d'une camera HTTP doit commencer par http:// ou https://")
        return v


class CameraCreate(CameraBase):
    id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if not _ID_RE.match(v):
            raise ValueError(
                "L'identifiant doit contenir uniquement des lettres minuscules, "
                "chiffres, tirets ou underscores (2-64 caracteres)"
            )
        return v


class CameraUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    source_type: Optional[SourceType] = None
    url: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    live_url: Optional[str] = Field(default=None, max_length=2000)
    enabled: Optional[bool] = None
    record: Optional[bool] = None


class Camera(CameraBase):
    id: str


class CameraStatus(BaseModel):
    id: str
    running: bool
    state: str  # stopped | starting | running | error | disabled
    last_error: Optional[str] = None
    restart_count: int = 0
    started_at: Optional[str] = None


class CameraWithStatus(Camera):
    status: CameraStatus
