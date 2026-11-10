"""Data models, split by domain (one file per concern, mirroring the
app/*_store.py persistence layer) so a change to one domain's models
can't accidentally touch another's.

Re-exports everything here so every existing `from app.models import X`
elsewhere in the codebase keeps working unchanged - this split only
reorganizes where each model *lives*, not how it's imported.
"""
from __future__ import annotations

from app.models.camera import (
    MOTION_GRID_CELLS,
    MOTION_GRID_COLS,
    MOTION_GRID_ROWS,
    SCHEDULE_CELLS,
    SCHEDULE_DAYS,
    SCHEDULE_HOURS,
    Camera,
    CameraBase,
    CameraCreate,
    CameraStatus,
    CameraUpdate,
    CameraWithStatus,
    SourceType,
    schedule_allows_recording,
)
from app.models.notifications import (
    NotificationSettings,
    NotificationSettingsBase,
    NotificationSettingsUpdate,
)
from app.models.router_credentials import (
    RouterCredentials,
    RouterCredentialsBase,
    RouterCredentialsUpdate,
)
from app.models.settings import RuntimeSettingsOut, RuntimeSettingsUpdate
from app.models.systems import (
    RemoteSystem,
    RemoteSystemBase,
    RemoteSystemCreate,
    RemoteSystemUpdate,
)
from app.models.user import (
    ALL_PERMISSIONS,
    DEFAULT_VIEWER_PERMISSIONS,
    PasswordChange,
    Permission,
    User,
    UserBase,
    UserCreate,
    UserPublic,
    UserRole,
    UserUpdate,
    can_access_camera,
    effective_permissions,
    has_permission,
)

__all__ = [
    "MOTION_GRID_CELLS",
    "MOTION_GRID_COLS",
    "MOTION_GRID_ROWS",
    "SCHEDULE_CELLS",
    "SCHEDULE_DAYS",
    "SCHEDULE_HOURS",
    "Camera",
    "CameraBase",
    "CameraCreate",
    "CameraStatus",
    "CameraUpdate",
    "CameraWithStatus",
    "SourceType",
    "schedule_allows_recording",
    "NotificationSettings",
    "NotificationSettingsBase",
    "NotificationSettingsUpdate",
    "RouterCredentials",
    "RouterCredentialsBase",
    "RouterCredentialsUpdate",
    "RuntimeSettingsOut",
    "RuntimeSettingsUpdate",
    "RemoteSystem",
    "RemoteSystemBase",
    "RemoteSystemCreate",
    "RemoteSystemUpdate",
    "ALL_PERMISSIONS",
    "DEFAULT_VIEWER_PERMISSIONS",
    "PasswordChange",
    "Permission",
    "User",
    "UserBase",
    "UserCreate",
    "UserPublic",
    "UserRole",
    "UserUpdate",
    "can_access_camera",
    "effective_permissions",
    "has_permission",
]
