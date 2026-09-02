from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import (
    routes_auth,
    routes_cameras,
    routes_media,
    routes_motion,
    routes_onvif,
    routes_ptz,
    routes_settings,
    routes_system,
    routes_users,
)
from app.auth import AuthService, bootstrap_admin
from app.config import get_settings
from app.ffmpeg_manager import StreamManager
from app.motion import MotionRegistry, motion_loop
from app.ptz_registry import PTZRegistry
from app.retention import retention_loop
from app.settings_store import SettingsStore
from app.store import CameraStore
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
    app.state.user_store = UserStore(settings.users_file)
    bootstrap_admin(settings, app.state.user_store)
    app.state.auth_service = AuthService(settings, app.state.user_store)
    app.state.stream_manager = StreamManager(settings)
    app.state.ptz_registry = PTZRegistry()
    app.state.motion_registry = MotionRegistry(settings.motion_dir)

    await app.state.stream_manager.reconcile(app.state.store.list())

    stop_event = asyncio.Event()
    app.state.retention_stop_event = stop_event
    retention_task = asyncio.create_task(retention_loop(settings, stop_event))
    thumbnail_task = asyncio.create_task(thumbnail_loop(settings, app.state.store, stop_event))
    motion_task = asyncio.create_task(motion_loop(settings, app.state.store, app.state.motion_registry, stop_event))

    try:
        yield
    finally:
        stop_event.set()
        await retention_task
        await thumbnail_task
        await motion_task
        await app.state.stream_manager.stop_all()


def create_app() -> FastAPI:
    app = FastAPI(title="NVR", lifespan=lifespan)

    app.include_router(routes_auth.router)
    app.include_router(routes_cameras.router)
    app.include_router(routes_media.router)
    app.include_router(routes_ptz.router)
    app.include_router(routes_motion.router)
    app.include_router(routes_onvif.router)
    app.include_router(routes_system.router)
    app.include_router(routes_users.router)
    app.include_router(routes_settings.router)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app


app = create_app()
