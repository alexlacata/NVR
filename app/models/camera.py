"""Camera domain: configuration, status, scheduling."""
from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.common import _ID_RE


class SourceType(str, Enum):
    rtsp = "rtsp"       # rtsp://... IP camera - the vast majority of them
                          # (Hikvision, Uniview, Dahua, Axis, Reolink, ONVIF...)
    rtmp = "rtmp"       # rtmp(s)://... push-style stream (encoders, some NVR relays)
    srt = "srt"         # srt://... low-latency, loss-resilient transport - a good
                          # fit for a flaky cellular/Peplink uplink when the
                          # camera or an intermediate encoder supports it
    http = "http"       # http(s):// MJPEG/HTTP video stream
    usb = "usb"         # local capture device, e.g. /dev/video0
    test = "test"       # synthetic test pattern, useful to validate the pipeline
                          # without an actual camera attached


_RESOLUTION_RE = re.compile(r"^\d{2,5}x\d{2,5}$")

# Motion mask grid: a fixed-size, coarse grid of on/off cells the user
# toggles over a camera snapshot to exclude areas (a road, a tree, a
# neighbour's window) from motion detection. Row-major, GRID_COLS wide by
# GRID_ROWS tall. Deliberately coarse (a handful of clicks covers a zone)
# rather than freehand rectangles, to keep both the UI and the model simple.
MOTION_GRID_COLS = 8
MOTION_GRID_ROWS = 6
MOTION_GRID_CELLS = MOTION_GRID_COLS * MOTION_GRID_ROWS

# Weekly recording schedule grid: 7 days (Monday=0 .. Sunday=6) x 24 hours,
# row-major (day * 24 + hour), true = record during that hour.
SCHEDULE_DAYS = 7
SCHEDULE_HOURS = 24
SCHEDULE_CELLS = SCHEDULE_DAYS * SCHEDULE_HOURS


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
    # Optional weekly timer restricting *when* `record` actually records:
    # empty = record continuously whenever `record` is true (prior
    # behavior); otherwise exactly SCHEDULE_CELLS booleans (see
    # schedule_allows_recording below), true = record during that hour.
    record_schedule: list[bool] = Field(default_factory=list)

    @field_validator("record_schedule")
    @classmethod
    def validate_record_schedule(cls, v: list[bool]) -> list[bool]:
        if v and len(v) != SCHEDULE_CELLS:
            raise ValueError(f"record_schedule doit contenir {SCHEDULE_CELLS} valeurs (7 jours x 24 heures) ou etre vide")
        return v

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
    # Speed (1-100%) of a continuous-move command, sent straight through as
    # the ONVIF ContinuousMove velocity (see OnvifPTZClient.continuous_move):
    # 100 = full speed (velocity 1.0), 50 = half speed, etc. Separate dials
    # for pan/tilt vs zoom since a camera's zoom motor is often much
    # slower/faster than its pan/tilt motor - one speed rarely suits both.
    ptz_pan_tilt_speed: int = Field(default=50, ge=1, le=100)
    ptz_zoom_speed: int = Field(default=50, ge=1, le=100)

    # Login for the camera's own web admin page (its native interface, not
    # this NVR) - used only to build the one-click "already logged in"
    # shortcut on the dashboard (see app/static/js/app.js buildDeviceLinks).
    # Left empty, that shortcut falls back to onvif_username/onvif_password
    # when set (often the same account) rather than asking for it twice.
    web_username: Optional[str] = Field(default=None, max_length=200)
    web_password: Optional[str] = Field(default=None, max_length=200)
    # Many camera admin pages are HTTPS-only (typically with a self-signed
    # certificate) - toggle this instead of the shortcut always assuming
    # plain HTTP.
    web_use_https: bool = False

    # SSH quick-access (username/port only, deliberately no password field):
    # there's no safe way to auto-authenticate SSH from a link the way HTTP
    # Basic Auth allows, and storing an SSH password would be far riskier
    # than the web login above - this only builds a ready ssh:// link and a
    # copy-paste command, never a stored credential. Most consumer cameras
    # don't expose SSH at all; leave blank when that's the case.
    ssh_username: Optional[str] = Field(default=None, max_length=200)
    ssh_port: Optional[int] = Field(default=None, ge=1, le=65535)

    # How often a thumbnail is extracted from this camera's recordings, for
    # the playback timeline. None = use the server-wide default.
    thumbnail_interval_seconds: Optional[int] = Field(default=None, ge=5, le=3600)

    # Motion detection: periodically diffs a small downscaled grayscale
    # frame sampled from the camera's own live HLS segments already on
    # disk (no extra connection to the camera). motion_sensitivity is 0
    # (only large/close motion trips it) to 100 (trips on the slightest
    # change). motion_mask_grid is either empty (no zone selected) or
    # exactly MOTION_GRID_CELLS booleans; what a selected (true) cell means
    # depends on motion_mask_mode:
    # - "exclude" (default, prior behavior): selected cells are ignored,
    #   everything else is monitored - a "zone a ignorer" (mask a specific
    #   spot like a road or a tree moving in the wind out of an otherwise
    #   fully-monitored scene).
    # - "include": only selected cells are monitored, everything else is
    #   ignored - a "zone a surveiller" (watch only a specific area, e.g. a
    #   doorway, instead of the whole frame). An include-mode camera with
    #   no cell selected monitors nothing at all - a real, if unusual,
    #   configuration (not a bug) rather than silently falling back to
    #   "monitor everything".
    motion_enabled: bool = False
    motion_sensitivity: int = Field(default=50, ge=0, le=100)
    motion_mask_mode: Literal["exclude", "include"] = "exclude"
    motion_mask_grid: list[bool] = Field(default_factory=list)

    @field_validator("motion_mask_grid")
    @classmethod
    def validate_motion_mask_grid(cls, v: list[bool]) -> list[bool]:
        if v and len(v) != MOTION_GRID_CELLS:
            raise ValueError(f"motion_mask_grid doit contenir {MOTION_GRID_CELLS} valeurs (ou etre vide)")
        return v

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str, info) -> str:
        source_type = info.data.get("source_type")
        v = v.strip()
        required_scheme = {
            SourceType.rtsp: ("rtsp://",),
            SourceType.rtmp: ("rtmp://", "rtmps://"),
            SourceType.srt: ("srt://",),
            SourceType.http: ("http://", "https://"),
        }.get(source_type)
        if required_scheme and "://" not in v:
            # Bare IP/host ("192.168.1.50" or "192.168.1.50:554/stream1"),
            # the common case when adding a camera "by IP" without knowing
            # to type a URL scheme - assume the scheme for this source type
            # instead of rejecting it.
            v = required_scheme[0] + v
        if required_scheme and not v.startswith(required_scheme):
            raise ValueError(f"L'URL doit commencer par {' ou '.join(required_scheme)}")
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
    ptz_pan_tilt_speed: Optional[int] = Field(default=None, ge=1, le=100)
    ptz_zoom_speed: Optional[int] = Field(default=None, ge=1, le=100)
    web_username: Optional[str] = Field(default=None, max_length=200)
    web_password: Optional[str] = Field(default=None, max_length=200)
    web_use_https: Optional[bool] = None
    ssh_username: Optional[str] = Field(default=None, max_length=200)
    ssh_port: Optional[int] = Field(default=None, ge=1, le=65535)
    thumbnail_interval_seconds: Optional[int] = Field(default=None, ge=5, le=3600)
    motion_enabled: Optional[bool] = None
    motion_sensitivity: Optional[int] = Field(default=None, ge=0, le=100)
    motion_mask_mode: Optional[Literal["exclude", "include"]] = None
    motion_mask_grid: Optional[list[bool]] = None
    record_schedule: Optional[list[bool]] = None


class Camera(CameraBase):
    id: str


def schedule_allows_recording(camera: Camera, now: datetime) -> bool:
    """Whether `camera`'s weekly timer allows recording at `now` (local
    time). An empty record_schedule means "no restriction" - continuous
    recording whenever camera.record is true, the behavior before this
    field existed."""
    if not camera.record_schedule:
        return True
    slot = now.weekday() * SCHEDULE_HOURS + now.hour
    return camera.record_schedule[slot]


class CameraStatus(BaseModel):
    id: str
    running: bool
    state: str  # stopped | starting | running | error | disabled
    last_error: Optional[str] = None
    restart_count: int = 0
    started_at: Optional[str] = None


class CameraWithStatus(Camera):
    status: CameraStatus

