"""User/auth domain: accounts, roles, permissions."""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

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
    # Which cameras this account can see at all, by id. None (the default)
    # means every camera - the behavior before per-camera restrictions
    # existed, and always the case for an admin regardless of what's stored
    # here (see can_access_camera()). An empty list means "no cameras",
    # a real (if unusual) state an admin might set deliberately. Stale ids
    # (a camera later deleted) are harmless - they just never match.
    allowed_camera_ids: Optional[list[str]] = None

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


def can_access_camera(user: "UserBase", camera_id: str) -> bool:
    """Whether `user` can see/use `camera_id` at all. An admin always can;
    a viewer can unless restricted to a specific list that excludes it."""
    if user.role == UserRole.admin:
        return True
    if user.allowed_camera_ids is None:
        return True
    return camera_id in user.allowed_camera_ids


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=200)


class UserUpdate(BaseModel):
    role: Optional[UserRole] = None
    permissions: Optional[list[Permission]] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=200)
    # None is a real value here (see UserBase.allowed_camera_ids), so
    # UserStore.update() distinguishes "not provided" from "provided as
    # null" via model_fields_set rather than the `is not None` check used
    # for the fields above.
    allowed_camera_ids: Optional[list[str]] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class User(UserBase):
    password_hash: str
    created_at: str
    # 2FA (TOTP): totp_secret is set (pending) as soon as enrollment starts,
    # but totp_enabled only flips to True once the user proves they can
    # generate a valid code with it (see /api/auth/totp/confirm) - so a
    # half-finished enrollment never silently protects (or locks out) the
    # account.
    totp_secret: Optional[str] = None
    totp_enabled: bool = False
    # Hashed (passlib, like password_hash) one-time backup codes - never
    # stored or compared in plaintext. Consumed (removed) on use.
    totp_recovery_codes: list[str] = Field(default_factory=list)


class UserPublic(UserBase):
    created_at: str
    totp_enabled: bool = False

