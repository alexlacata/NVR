from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Request, status

from app.audit_log import AuditLog
from app.auth import COOKIE_NAME, AuthService
from app.backup import BackupStatusTracker
from app.config import Settings
from app.ffmpeg_manager import StreamManager
from app.login_throttle import LoginThrottle
from app.models import Permission, User, UserRole, can_access_camera, has_permission
from app.motion import MotionRegistry
from app.notification_settings_store import NotificationSettingsStore
from app.notifier import Notifier
from app.ptz_registry import PTZRegistry
from app.router_credentials_store import RouterCredentialsStore
from app.session_store import SessionStore
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


def get_hw_encoder(request: Request) -> Optional[str]:
    """The hardware video encoder resolved at startup (see
    app.hw_encoder.detect_hw_encoder), or None when falling back to
    software (libx264) - e.g. on a Raspberry Pi 5, a PC, or any host
    without a working h264_v4l2m2m."""
    return getattr(request.app.state, "hw_encoder", None)


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


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.session_store


def get_router_credentials_store(request: Request) -> RouterCredentialsStore:
    return request.app.state.router_credentials_store


def _extract_token(request: Request) -> Optional[str]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization[7:]
    return token


def require_auth(request: Request) -> User:
    auth_service: AuthService = request.app.state.auth_service
    token = _extract_token(request)
    user = auth_service.verify_token(token) if token else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentification requise")
    return user


def get_current_jti(request: Request) -> Optional[str]:
    """The session id embedded in the caller's own token, if any - used to
    mark "this is the session you're using right now" in the sessions
    list, and to revoke exactly that one on logout."""
    auth_service: AuthService = request.app.state.auth_service
    token = _extract_token(request)
    return auth_service.session_id_from_token(token) if token else None


def ensure_camera_access(user: User, camera_id: str) -> None:
    """Raises 404 - not 403 - when `user` is a viewer restricted to a set of
    cameras that doesn't include `camera_id`, so a restricted account can't
    tell "exists but I can't see it" apart from "doesn't exist" (same
    detail text CameraNotFound already uses for the latter)."""
    if not can_access_camera(user, camera_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera introuvable")


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
