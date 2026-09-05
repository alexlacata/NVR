from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.audit_log import AuditLog
from app.auth import COOKIE_NAME, AuthService
from app.backup import BackupStatusTracker
from app.config import Settings
from app.ffmpeg_manager import StreamManager
from app.login_throttle import LoginThrottle
from app.models import Permission, User, UserRole, has_permission
from app.motion import MotionRegistry
from app.notification_settings_store import NotificationSettingsStore
from app.notifier import Notifier
from app.ptz_registry import PTZRegistry
from app.settings_store import SettingsStore
from app.store import CameraStore
from app.systems_store import RemoteSystemStore
from app.user_store import UserStore


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> CameraStore:
    return request.app.state.store


def get_user_store(request: Request) -> UserStore:
    return request.app.state.user_store


def get_stream_manager(request: Request) -> StreamManager:
    return request.app.state.stream_manager


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


def get_ptz_registry(request: Request) -> PTZRegistry:
    return request.app.state.ptz_registry


def get_motion_registry(request: Request) -> MotionRegistry:
    return request.app.state.motion_registry


def get_settings_store(request: Request) -> SettingsStore:
    return request.app.state.settings_store


def get_systems_store(request: Request) -> RemoteSystemStore:
    return request.app.state.systems_store


def get_login_throttle(request: Request) -> LoginThrottle:
    return request.app.state.login_throttle


def get_notification_settings_store(request: Request) -> NotificationSettingsStore:
    return request.app.state.notification_settings_store


def get_notifier(request: Request) -> Notifier:
    return request.app.state.notifier


def get_audit_log(request: Request) -> AuditLog:
    return request.app.state.audit_log


def get_backup_status(request: Request) -> BackupStatusTracker:
    return request.app.state.backup_status


def require_auth(request: Request) -> User:
    auth_service: AuthService = request.app.state.auth_service
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization[7:]
    user = auth_service.verify_token(token) if token else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentification requise")
    return user


def require_admin(request: Request) -> User:
    user = require_auth(request)
    if user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reserve aux administrateurs")
    return user


def require_permission(permission: Permission):
    """Dependency factory for one operational permission (see Permission in
    models.py). An admin always passes, regardless of their stored
    permissions list. Account/user management stays exclusively behind
    require_admin - it is intentionally not one of these permissions, so a
    viewer granted extra permissions can never create/promote accounts."""

    def _check(request: Request) -> User:
        user = require_auth(request)
        if not has_permission(user, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission manquante")
        return user

    return _check


# Precomputed (not called per-request) so the same callable is reused
# everywhere a given permission is required, letting FastAPI's
# per-request dependency cache treat repeated Depends(...) on it (e.g.
# router-level and again as a route parameter) as a single check.
require_cameras_manage = require_permission(Permission.cameras_manage)
require_ptz_control = require_permission(Permission.ptz_control)
require_recordings_delete = require_permission(Permission.recordings_delete)
require_recordings_download = require_permission(Permission.recordings_download)
require_settings_manage = require_permission(Permission.settings_manage)
