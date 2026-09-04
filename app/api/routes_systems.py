"""Directory of *other* NVR systems (each a fully separate installation)
that this one links out to - not this NVR's own cameras (see
routes_cameras.py). Reachability is intentionally not tracked here: it
depends on where the viewer's own device currently is (local network,
VPN, elsewhere), so each browser checks it directly - see systems.html."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_systems_store, require_auth, require_settings_manage
from app.models import RemoteSystem, RemoteSystemCreate, RemoteSystemUpdate
from app.systems_store import DuplicateRemoteSystemId, RemoteSystemNotFound, RemoteSystemStore

router = APIRouter(prefix="/api/systems", tags=["systems"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[RemoteSystem])
def list_systems(store: RemoteSystemStore = Depends(get_systems_store)):
    return store.list()


@router.post("", response_model=RemoteSystem, status_code=201, dependencies=[Depends(require_settings_manage)])
def create_system(
    payload: RemoteSystemCreate,
    store: RemoteSystemStore = Depends(get_systems_store),
):
    try:
        return store.create(payload)
    except DuplicateRemoteSystemId:
        raise HTTPException(status_code=409, detail="Cet identifiant de systeme existe deja")


@router.patch("/{system_id}", response_model=RemoteSystem, dependencies=[Depends(require_settings_manage)])
def update_system(
    system_id: str,
    payload: RemoteSystemUpdate,
    store: RemoteSystemStore = Depends(get_systems_store),
):
    try:
        return store.update(system_id, payload)
    except RemoteSystemNotFound:
        raise HTTPException(status_code=404, detail="Systeme introuvable")


@router.delete("/{system_id}", status_code=204, dependencies=[Depends(require_settings_manage)])
def delete_system(
    system_id: str,
    store: RemoteSystemStore = Depends(get_systems_store),
):
    try:
        store.delete(system_id)
    except RemoteSystemNotFound:
        raise HTTPException(status_code=404, detail="Systeme introuvable")
    return None
