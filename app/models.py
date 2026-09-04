"""Data models for cameras."""
from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-_]{1,63}$")


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

    # How often a thumbnail is extracted from this camera's recordings, for
    # the playback timeline. None = use the server-wide default.
    thumbnail_interval_seconds: Optional[int] = Field(default=None, ge=5, le=3600)

    # Motion detection: periodically diffs a small downscaled grayscale
    # frame sampled from the camera's own live HLS segments already on
    # disk (no extra connection to the camera). motion_sensitivity is 0
    # (only large/close motion trips it) to 100 (trips on the slightest
    # change). motion_mask_grid is either empty (no zone excluded) or
    # exactly MOTION_GRID_CELLS booleans, true = excluded from detection.
    motion_enabled: bool = False
    motion_sensitivity: int = Field(default=50, ge=0, le=100)
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
    thumbnail_interval_seconds: Optional[int] = Field(default=None, ge=5, le=3600)
    motion_enabled: Optional[bool] = None
    motion_sensitivity: Optional[int] = Field(default=None, ge=0, le=100)
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


_USERNAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{2,63}$")


class UserRole(str, Enum):
    admin = "admin"     # always has every permission below, and is the only
                          # role that can manage accounts (create/edit/delete
                          # users, change roles/permissions) - this stays a
                          # hardcoded, non-delegable boundary so a viewer
                          # granted extra permissions can never promote
                          # themselves or anyone else to admin.
    viewer = "viewer"   # views live/recordings by default; an admin can grant
                          # a specific viewer additional Permission values
                          # below (e.g. managing cameras) without making them
                          # a full administrator.


class Permission(str, Enum):
    cameras_manage = "cameras_manage"            # add/edit/delete cameras, ONVIF setup
    ptz_control = "ptz_control"                  # pilot PTZ (pan/tilt/zoom, presets)
    recordings_delete = "recordings_delete"      # delete individual recordings
    recordings_download = "recordings_download"  # save a recording to the device (separate from watching it inline)
    settings_manage = "settings_manage"          # server-wide retention/HLS/thumbnail settings


ALL_PERMISSIONS: list[Permission] = list(Permission)

# What a newly created viewer can do out of the box, matching the
# behavior before per-user permissions existed (PTZ was unconditionally
# available to any logged-in user, nothing else was - and so was
# downloading a recording, there was no separate endpoint for it).
DEFAULT_VIEWER_PERMISSIONS: list[Permission] = [Permission.ptz_control, Permission.recordings_download]


class UserBase(BaseModel):
    username: str
    role: UserRole = UserRole.viewer
    # Only meaningful for role=viewer - an admin always has every permission
    # regardless of what's stored here (see effective_permissions()).
    permissions: list[Permission] = Field(default_factory=lambda: list(DEFAULT_VIEWER_PERMISSIONS))

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if not _USERNAME_RE.match(v):
            raise ValueError(
                "Le nom d'utilisateur doit faire 3-64 caracteres : lettres, chiffres, "
                "points, tirets ou underscores, et ne peut pas commencer par un symbole"
            )
        return v


def effective_permissions(user: "UserBase") -> set[Permission]:
    """Permissions actually granted to this account: all of them for an
    admin (hardcoded, not driven by the stored list), or the account's own
    stored list for a viewer."""
    if user.role == UserRole.admin:
        return set(ALL_PERMISSIONS)
    return set(user.permissions)


def has_permission(user: "UserBase", permission: Permission) -> bool:
    return permission in effective_permissions(user)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=200)


class UserUpdate(BaseModel):
    role: Optional[UserRole] = None
    permissions: Optional[list[Permission]] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=200)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class User(UserBase):
    password_hash: str
    created_at: str


class UserPublic(UserBase):
    created_at: str


class RuntimeSettingsUpdate(BaseModel):
    retention_days: Optional[int] = Field(default=None, ge=1, le=3650)
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


# A directory of *other* NVR installations (each a fully separate system -
# its own cameras, its own accounts, its own disk) that this one simply
# links out to, for someone managing several sites. Deliberately just a
# name + address + note: reachability is checked client-side (each
# viewer's own browser, since whether an address is reachable depends on
# where that person currently is, not on this server) rather than stored,
# and clicking through opens that other system's own login page - there is
# no shared auth or data between entries.
class RemoteSystemBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=300)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("L'adresse ne peut pas etre vide")
        if "://" not in v:
            v = f"http://{v}"
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("L'adresse doit etre une URL http(s):// (ou juste une IP/nom d'hote)")
        return v.rstrip("/")


class RemoteSystemCreate(RemoteSystemBase):
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


class RemoteSystemUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    url: Optional[str] = Field(default=None, min_length=1, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=300)


class RemoteSystem(RemoteSystemBase):
    id: str
