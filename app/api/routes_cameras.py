from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_ptz_registry, get_settings, get_store, get_stream_manager, require_auth
from app.ffmpeg_manager import StreamManager
from app.models import Camera, CameraCreate, CameraUpdate, CameraWithStatus
from app.ptz_registry import PTZRegistry
from app.store import CameraNotFound, CameraStore, DuplicateCameraId

router = APIRouter(prefix="/api/cameras", tags=["cameras"], dependencies=[Depends(require_auth)])


def _with_status(camera: Camera, manager: StreamManager) -> CameraWithStatus:
    return CameraWithStatus(**camera.model_dump(), status=manager.status(camera.id))


@router.get("", response_model=list[CameraWithStatus])
def list_cameras(
    store: CameraStore = Depends(get_store),
    manager: StreamManager = Depends(get_stream_manager),
):
    return [_with_status(c, manager) for c in store.list()]


@router.post("", response_model=CameraWithStatus, status_code=201)
async def create_camera(
    payload: CameraCreate,
    store: CameraStore = Depends(get_store),
    manager: StreamManager = Depends(get_stream_manager),
):
    try:
        camera = store.create(payload)
    except DuplicateCameraId:
        raise HTTPException(status_code=409, detail="Cet identifiant de camera existe deja")
    await manager.reconcile(store.list())
    return _with_status(camera, manager)


@router.get("/{camera_id}", response_model=CameraWithStatus)
def get_camera(
    camera_id: str,
    store: CameraStore = Depends(get_store),
    manager: StreamManager = Depends(get_stream_manager),
):
    try:
        camera = store.get(camera_id)
    except CameraNotFound:
        raise HTTPException(status_code=404, detail="Camera introuvable")
    return _with_status(camera, manager)


@router.patch("/{camera_id}", response_model=CameraWithStatus)
async def update_camera(
    camera_id: str,
    payload: CameraUpdate,
    store: CameraStore = Depends(get_store),
    manager: StreamManager = Depends(get_stream_manager),
):
    try:
        camera = store.update(camera_id, payload)
    except CameraNotFound:
        raise HTTPException(status_code=404, detail="Camera introuvable")
    await manager.reconcile(store.list())
    return _with_status(camera, manager)


@router.delete("/{camera_id}", status_code=204)
async def delete_camera(
    camera_id: str,
    delete_recordings: bool = False,
    store: CameraStore = Depends(get_store),
    manager: StreamManager = Depends(get_stream_manager),
    settings=Depends(get_settings),
    ptz_registry: PTZRegistry = Depends(get_ptz_registry),
):
    try:
        store.delete(camera_id)
    except CameraNotFound:
        raise HTTPException(status_code=404, detail="Camera introuvable")
    await manager.reconcile(store.list())
    ptz_registry.invalidate(camera_id)
    shutil.rmtree(settings.hls_dir / camera_id, ignore_errors=True)
    if delete_recordings:
        shutil.rmtree(settings.recordings_dir / camera_id, ignore_errors=True)
    return None
