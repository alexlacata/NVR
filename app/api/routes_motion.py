"""Read-only motion detection status - current state plus recent events -
for a camera. Enabling/configuring motion detection itself (motion_enabled,
motion_sensitivity, motion_mask_grid) goes through PATCH /api/cameras/{id}
like any other camera field, gated by the same cameras_manage permission."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import get_motion_registry, get_store, require_auth
from app.models import MOTION_GRID_COLS, MOTION_GRID_ROWS
from app.motion import MotionRegistry
from app.store import CameraNotFound, CameraStore

router = APIRouter(prefix="/api/cameras/{camera_id}/motion", tags=["motion"], dependencies=[Depends(require_auth)])


class MotionEventOut(BaseModel):
    at: str
    ratio: float


class MotionStatusOut(BaseModel):
    active: bool
    last_ratio: float
    last_checked_at: str | None
    last_motion_at: str | None
    grid_cols: int
    grid_rows: int
    recent_events: list[MotionEventOut]


@router.get("", response_model=MotionStatusOut)
def get_motion_status(
    camera_id: str,
    store: CameraStore = Depends(get_store),
    registry: MotionRegistry = Depends(get_motion_registry),
):
    try:
        store.get(camera_id)
    except CameraNotFound:
        raise HTTPException(status_code=404, detail="Camera introuvable")
    state = registry.state(camera_id)
    events = registry.recent_events(camera_id)
    return MotionStatusOut(
        active=state.active,
        last_ratio=state.last_ratio,
        last_checked_at=state.last_checked_at,
        last_motion_at=state.last_motion_at,
        grid_cols=MOTION_GRID_COLS,
        grid_rows=MOTION_GRID_ROWS,
        recent_events=[MotionEventOut(**e) for e in events],
    )
