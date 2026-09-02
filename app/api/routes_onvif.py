"""ONVIF discovery endpoints, usable before a camera has been created:
these help fill in a camera's URL field rather than manage an existing
camera (that's routes_ptz.py)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps import require_cameras_manage
from app.onvif_client import OnvifError, probe_media
from app.onvif_discovery import discover_onvif_devices

# Camera setup actions - not needed to just watch/operate a camera, so
# gated behind the same permission as the rest of camera configuration.
router = APIRouter(prefix="/api/onvif", tags=["onvif"], dependencies=[Depends(require_cameras_manage)])


class ProbeRequest(BaseModel):
    onvif_url: str = Field(min_length=1, max_length=2000)
    username: str = ""
    password: str = ""


class ProfileOut(BaseModel):
    token: str
    name: str
    resolution: str | None
    stream_uri: str | None


@router.post("/probe", response_model=list[ProfileOut])
async def probe(payload: ProbeRequest):
    url = payload.onvif_url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="L'URL ONVIF doit commencer par http:// ou https://")
    try:
        profiles = await probe_media(url, payload.username, payload.password)
    except OnvifError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    if not profiles:
        raise HTTPException(status_code=404, detail="Aucun profil media trouve sur cette camera")
    return [
        ProfileOut(token=p.token, name=p.name, resolution=p.resolution, stream_uri=p.stream_uri)
        for p in profiles
    ]


@router.post("/discover")
async def discover(timeout_seconds: float = 3.0):
    timeout_seconds = max(1.0, min(timeout_seconds, 10.0))
    try:
        devices = await discover_onvif_devices(timeout_seconds=timeout_seconds)
    except OSError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Balayage reseau impossible depuis ce serveur "
                f"({exc}). En Docker, le conteneur doit utiliser le reseau hote "
                "(network_mode: host) pour recevoir les reponses multicast."
            ),
        )
    return devices
