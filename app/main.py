from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import (
    routes_audit,
    routes_auth,
    routes_backup,
    routes_cameras,
    routes_media,
    routes_motion,
    routes_notifications,
    routes_onvif,
    routes_ptz,
    routes_settings,
    routes_system,
    routes_systems,
    routes_users,
)
from app.audit_log import AuditLog
from app.auth import AuthService, bootstrap_admin
from app.backup import BackupStatusTracker, backup_loop
from app.camera_health import CameraHealthRegistry, camera_health_loop
from app.config import get_settings
from app.ffmpeg_manager import StreamManager
from app.login_throttle import LoginThrottle
from app.motion import MotionRegistry, motion_loop
from app.notification_settings_store import NotificationSettingsStore
from app.notifier import Notifier
from app.ptz_registry import PTZRegistry
from app.recording_schedule import recording_schedule_loop
from app.retention import retention_loop
from app.settings_store import SettingsStore
from app.store import CameraStore
from app.systems_store import RemoteSystemStore
from app.thumbnails import thumbnail_loop
from app.user_store import UserStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()

    app.state.settings_store = SettingsStore(settings.runtime_settings_file)
    app.state.settings_store.apply_to(settings)

    app.state.settings = settings
    app.state.store = CameraStore(settings.cameras_file)
    app.state.systems_store = RemoteSystemStore(settings.systems_file)
    app.state.user_store = UserStore(settings.users_file)
    bootstrap_admin(settings, app.state.user_store)
    app.state.auth_service = AuthService(settings, app.state.user_store)
    app.state.login_throttle = LoginThrottle(
        max_attempts=settings.login_max_attempts,
        window_seconds=settings.login_attempt_window_seconds,
        lockout_seconds=settings.login_lockout_seconds,
    )
    app.state.stream_manager = StreamManager(settings)
    app.state.ptz_registry = PTZRegistry()
    app.state.motion_registry = MotionRegistry(settings.motion_dir)
    app.state.notification_settings_store = NotificationSettingsStore(settings.notification_settings_file)
    app.state.notifier = Notifier(app.state.notification_settings_store)
    app.state.camera_health_registry = CameraHealthRegistry()
    app.state.audit_log = AuditLog(settings.audit_log_file)
    app.state.backup_status = BackupStatusTracker()

    await app.state.stream_manager.reconcile(app.state.store.list())

    stop_event = asyncio.Event()
    app.state.retention_stop_event = stop_event
    retention_task = asyncio.create_task(retention_loop(settings, stop_event, app.state.notifier))
    thumbnail_task = asyncio.create_task(thumbnail_loop(settings, app.state.store, stop_event))
    motion_task = asyncio.create_task(
        motion_loop(settings, app.state.store, app.state.motion_registry, stop_event, app.state.notifier)
    )
    schedule_task = asyncio.create_task(
        recording_schedule_loop(app.state.store, app.state.stream_manager, stop_event)
    )
    camera_health_task = asyncio.create_task(
        camera_health_loop(
            settings,
            app.state.store,
            app.state.stream_manager,
            app.state.notifier,
            app.state.camera_health_registry,
            stop_event,
        )
    )
    backup_task = asyncio.create_task(
        backup_loop(settings, stop_event, app.state.notifier, app.state.backup_status)
    )

    try:
        yield
    finally:
        stop_event.set()
        await retention_task
        await thumbnail_task
        await motion_task
        await schedule_task
        await camera_health_task
        await backup_task
        await app.state.stream_manager.stop_all()


def create_app() -> FastAPI:
    app = FastAPI(title="NVR", lifespan=lifespan)

    app.include_router(routes_auth.router)
    app.include_router(routes_cameras.router)
    app.include_router(routes_media.router)
    app.include_router(routes_ptz.router)
    app.include_router(routes_audit.router)
    app.include_router(routes_backup.router)
    app.include_router(routes_motion.router)
    app.include_router(routes_notifications.router)
    app.include_router(routes_onvif.router)
    app.include_router(routes_system.router)
    app.include_router(routes_systems.router)
    app.include_router(routes_users.router)
    app.include_router(routes_settings.router)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app


app = create_app()


def run_server() -> None:
    """Entry point for `python -m app.main` - unlike the plain `uvicorn
    app.main:app` CLI invocation, this reads NVR_SSL_CERTFILE/
    NVR_SSL_KEYFILE and serves native HTTPS when both are set (see
    Settings.ssl_certfile/ssl_keyfile)."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        ssl_certfile=settings.ssl_certfile or None,
        ssl_keyfile=settings.ssl_keyfile or None,
    )


if __name__ == "__main__":
    run_server()
