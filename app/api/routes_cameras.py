from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends, HTTPException

from app.deps import (
    ensure_camera_access,
    get_motion_registry,
    get_ptz_registry,
    get_settings,
    get_store,
    get_stream_manager,
    require_auth,
    require_cameras_manage,
)
from app.ffmpeg_manager import StreamManager
from app.models import Camera, CameraCreate, CameraUpdate, CameraWithStatus, Permission, User, can_access_camera, has_permission
from app.motion import MotionRegistry
from app.ptz_registry import PTZRegistry
from app.store import CameraNotFound, CameraStore, DuplicateCameraId

router = APIRouter(prefix="/api/cameras", tags=["cameras"], dependencies=[Depends(require_auth)])


def _with_status(camera: Camera, manager: StreamManager, user: User) -> CameraWithStatus:
    with_status = CameraWithStatus(**camera.model_dump(), status=manager.status(camera.id))
    # onvif_password/web_password can auto-authenticate into the camera's
    # own admin page (see app.js buildDeviceLinks) - viewers without
    # cameras_manage can still see/watch the camera, but shouldn't be
    # handed its admin credentials, so those two fields are blanked out
    # for them rather than gating the whole endpoint behind the permission.
    if not has_permission(user, Permission.cameras_manage):
        with_status = with_status.model_copy(update={"onvif_password": None, "web_password": None})
    return with_status


@router.get("", response_model=list[CameraWithStatus])
def list_cameras(
    store: CameraStore = Depends(get_store),
    manager: StreamManager = Depends(get_stream_manager),
    user: User = Depends(require_auth),
):
    return [_with_status(c, manager, user) for c in store.list() if can_access_camera(user, c.id)]


@router.post("", response_model=CameraWithStatus, status_code=201, dependencies=[Depends(require_cameras_manage)])
async def create_camera(
    payload: CameraCreate,
    store: CameraStore = Depends(get_store),
    manager: StreamManager = Depends(get_stream_manager),
    user: User = Depends(require_auth),
):
    try:
        camera = store.create(payload)
    except DuplicateCameraId:
        raise HTTPException(status_code=409, detail="Cet identifiant de camera existe deja")
    await manager.reconcile(store.list())
    return _with_status(camera, manager, user)


@router.get("/{camera_id}", response_model=CameraWithStatus)
def get_camera(
    camera_id: str,
    store: CameraStore = Depends(get_store),
    manager: StreamManager = Depends(get_stream_manager),
    user: User = Depends(require_auth),
):
    ensure_camera_access(user, camera_id)
    try:
        camera = store.get(camera_id)
    except CameraNotFound:
        raise HTTPException(status_code=404, detail="Camera introuvable")
    return _with_status(camera, manager, user)


@router.patch("/{camera_id}", response_model=CameraWithStatus, dependencies=[Depends(require_cameras_manage)])
async def update_camera(
    camera_id: str,
    payload: CameraUpdate,
    store: CameraStore = Depends(get_store),
    manager: StreamManager = Depends(get_stream_manager),
    user: User = Depends(require_auth),
):
    ensure_camera_access(user, camera_id)
    try:
        camera = store.update(camera_id, payload)
    except CameraNotFound:
        raise HTTPException(status_code=404, detail="Camera introuvable")
    await manager.reconcile(store.list())
    return _with_status(camera, manager, user)


@router.delete("/{camera_id}", status_code=204, dependencies=[Depends(require_cameras_manage)])
async def delete_camera(
    camera_id: str,
    delete_recordings: bool = False,
    store: CameraStore = Depends(get_store),
    manager: StreamManager = Depends(get_stream_manager),
    settings=Depends(get_settings),
    ptz_registry: PTZRegistry = Depends(get_ptz_registry),
    motion_registry: MotionRegistry = Depends(get_motion_registry),
    user: User = Depends(require_auth),
):
    ensure_camera_access(user, camera_id)
    try:
        store.delete(camera_id)
    except CameraNotFound:
        raise HTTPException(status_code=404, detail="Camera introuvable")
    await manager.reconcile(store.list())
    ptz_registry.invalidate(camera_id)
    motion_registry.invalidate(camera_id)
    shutil.rmtree(settings.hls_dir / camera_id, ignore_errors=True)
    if delete_recordings:
        shutil.rmtree(settings.recordings_dir / camera_id, ignore_errors=True)
    return None
