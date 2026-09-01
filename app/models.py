"""Data models for cameras."""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-_]{1,63}$")


class SourceType(str, Enum):
    rtsp = "rtsp"       # rtsp://... IP camera
    http = "http"       # http(s):// MJPEG/HTTP video stream
    usb = "usb"         # local capture device, e.g. /dev/video0
    test = "test"       # synthetic test pattern, useful to validate the pipeline
                          # without an actual camera attached


_RESOLUTION_RE = re.compile(r"^\d{2,5}x\d{2,5}$")


class CameraBase(BaseModel):
    # Needed so the ptz_enabled -> onvif_url cross-field check below also
    # fires when onvif_url is simply omitted (left at its default), not just
    # when it's explicitly passed as None.
    model_config = ConfigDict(validate_default=True)

    name: str = Field(min_length=1, max_length=100)
    source_type: SourceType = SourceType.rtsp
    url: str = Field(min_length=1, max_length=2000)
    # Optional lower-resolution "sub stream" URL used only for the live view,
    # while `url` (main stream) is used for recording. Leave empty to reuse
    # `url` for both. Only meaningful for rtsp/http sources.
    live_url: Optional[str] = Field(default=None, max_length=2000)
    enabled: bool = True
    record: bool = True

    # Caps the live/HLS leg's bitrate (kbps) and/or resolution, independent
    # of the recording leg which always stays full quality. Useful when the
    # live view travels over a constrained/metered uplink (e.g. a cellular
    # router such as a Peplink) while recording happens on the local disk.
    live_max_bitrate_kbps: Optional[int] = Field(default=None, ge=64, le=20000)
    live_scale: Optional[str] = Field(default=None, max_length=16)

    # PTZ (pan/tilt/zoom) control over ONVIF. `onvif_url` is the camera's
    # ONVIF device service URL, commonly http://<ip>:<port>/onvif/device_service.
    ptz_enabled: bool = False
    onvif_url: Optional[str] = Field(default=None, max_length=2000)
    onvif_username: Optional[str] = Field(default=None, max_length=200)
    onvif_password: Optional[str] = Field(default=None, max_length=200)

    # How often a thumbnail is extracted from this camera's recordings, for
    # the playback timeline. None = use the server-wide default.
    thumbnail_interval_seconds: Optional[int] = Field(default=None, ge=5, le=3600)

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

    @field_validator("live_scale")
    @classmethod
    def validate_live_scale(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        v = v.strip().lower()
        if not _RESOLUTION_RE.match(v):
            raise ValueError("La resolution doit etre au format LARGEURxHAUTEUR, ex. 854x480")
        return v

    @field_validator("onvif_url")
    @classmethod
    def validate_onvif_url(cls, v: Optional[str], info) -> Optional[str]:
        if v is None or v == "":
            if info.data.get("ptz_enabled"):
                raise ValueError("L'URL ONVIF est requise pour une camera PTZ")
            return None
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("L'URL ONVIF doit commencer par http:// ou https://")
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
    live_max_bitrate_kbps: Optional[int] = Field(default=None, ge=64, le=20000)
    live_scale: Optional[str] = Field(default=None, max_length=16)
    ptz_enabled: Optional[bool] = None
    onvif_url: Optional[str] = Field(default=None, max_length=2000)
    onvif_username: Optional[str] = Field(default=None, max_length=200)
    onvif_password: Optional[str] = Field(default=None, max_length=200)
    thumbnail_interval_seconds: Optional[int] = Field(default=None, ge=5, le=3600)


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
