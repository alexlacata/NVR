from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps import get_ptz_registry, get_store, require_auth
from app.models import Camera
from app.onvif_ptz import OnvifError
from app.ptz_registry import PTZRegistry
from app.store import CameraNotFound, CameraStore

router = APIRouter(prefix="/api/cameras/{camera_id}/ptz", tags=["ptz"], dependencies=[Depends(require_auth)])


class MoveRequest(BaseModel):
    pan: float = Field(default=0.0, ge=-1.0, le=1.0)
    tilt: float = Field(default=0.0, ge=-1.0, le=1.0)
    zoom: float = Field(default=0.0, ge=-1.0, le=1.0)


class PresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


def _require_ptz_camera(camera_id: str, store: CameraStore) -> Camera:
    try:
        camera = store.get(camera_id)
    except CameraNotFound:
        raise HTTPException(status_code=404, detail="Camera introuvable")
    if not camera.ptz_enabled or not camera.onvif_url:
        raise HTTPException(status_code=400, detail="Cette camera n'est pas configuree en PTZ")
    return camera


async def _client(camera: Camera, registry: PTZRegistry):
    return await registry.get(camera)


@router.post("/move")
async def move(
    camera_id: str,
    payload: MoveRequest,
    store: CameraStore = Depends(get_store),
    registry: PTZRegistry = Depends(get_ptz_registry),
):
    camera = _require_ptz_camera(camera_id, store)
    client = await _client(camera, registry)
    try:
        await client.continuous_move(payload.pan, payload.tilt, payload.zoom)
    except OnvifError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True}


@router.post("/stop")
async def stop(
    camera_id: str,
    store: CameraStore = Depends(get_store),
    registry: PTZRegistry = Depends(get_ptz_registry),
):
    camera = _require_ptz_camera(camera_id, store)
    client = await _client(camera, registry)
    try:
        await client.stop()
    except OnvifError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True}


@router.get("/presets")
async def list_presets(
    camera_id: str,
    store: CameraStore = Depends(get_store),
    registry: PTZRegistry = Depends(get_ptz_registry),
):
    camera = _require_ptz_camera(camera_id, store)
    client = await _client(camera, registry)
    try:
        presets = await client.get_presets()
    except OnvifError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return [{"token": p.token, "name": p.name} for p in presets]


@router.post("/presets", status_code=201)
async def create_preset(
    camera_id: str,
    payload: PresetCreate,
    store: CameraStore = Depends(get_store),
    registry: PTZRegistry = Depends(get_ptz_registry),
):
    camera = _require_ptz_camera(camera_id, store)
    client = await _client(camera, registry)
    try:
        token = await client.set_preset(payload.name)
    except OnvifError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"token": token, "name": payload.name}


@router.post("/presets/{preset_token}/goto")
async def goto_preset(
    camera_id: str,
    preset_token: str,
    store: CameraStore = Depends(get_store),
    registry: PTZRegistry = Depends(get_ptz_registry),
):
    camera = _require_ptz_camera(camera_id, store)
    client = await _client(camera, registry)
    try:
        await client.goto_preset(preset_token)
    except OnvifError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True}


@router.delete("/presets/{preset_token}", status_code=204)
async def delete_preset(
    camera_id: str,
    preset_token: str,
    store: CameraStore = Depends(get_store),
    registry: PTZRegistry = Depends(get_ptz_registry),
):
    camera = _require_ptz_camera(camera_id, store)
    client = await _client(camera, registry)
    try:
        await client.remove_preset(preset_token)
    except OnvifError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return None
