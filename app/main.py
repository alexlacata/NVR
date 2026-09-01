from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import routes_auth, routes_cameras, routes_media, routes_ptz, routes_system
from app.auth import AuthService
from app.config import get_settings
from app.ffmpeg_manager import StreamManager
from app.ptz_registry import PTZRegistry
from app.retention import retention_loop
from app.store import CameraStore
from app.thumbnails import thumbnail_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()

    app.state.settings = settings
    app.state.store = CameraStore(settings.cameras_file)
    app.state.auth_service = AuthService(settings)
    app.state.stream_manager = StreamManager(settings)
    app.state.ptz_registry = PTZRegistry()

    await app.state.stream_manager.reconcile(app.state.store.list())

    stop_event = asyncio.Event()
    app.state.retention_stop_event = stop_event
    retention_task = asyncio.create_task(retention_loop(settings, stop_event))
    thumbnail_task = asyncio.create_task(thumbnail_loop(settings, app.state.store, stop_event))

    try:
        yield
    finally:
        stop_event.set()
        await retention_task
        await thumbnail_task
        await app.state.stream_manager.stop_all()


def create_app() -> FastAPI:
    app = FastAPI(title="NVR", lifespan=lifespan)

    app.include_router(routes_auth.router)
    app.include_router(routes_cameras.router)
    app.include_router(routes_media.router)
    app.include_router(routes_ptz.router)
    app.include_router(routes_system.router)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app


app = create_app()
