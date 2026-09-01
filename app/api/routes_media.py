from __future__ import annotations

import asyncio
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse

from app.config import Settings
from app.deps import get_settings, get_store, require_auth
from app.store import CameraNotFound, CameraStore

router = APIRouter(prefix="/api/cameras", tags=["media"], dependencies=[Depends(require_auth)])

_HLS_NAME_RE = re.compile(r"^(stream\.m3u8|seg_\d+\.ts)$")
_RECORDING_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.mp4$")

_MIME_TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".ts": "video/mp2t",
    ".mp4": "video/mp4",
}


def _require_camera(camera_id: str, store: CameraStore) -> None:
    try:
        store.get(camera_id)
    except CameraNotFound:
        raise HTTPException(status_code=404, detail="Camera introuvable")


@router.get("/{camera_id}/live/{filename}")
def get_live_file(
    camera_id: str,
    filename: str,
    store: CameraStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
):
    _require_camera(camera_id, store)
    if not _HLS_NAME_RE.match(filename):
        raise HTTPException(status_code=400, detail="Nom de fichier invalide")
    path = settings.hls_dir / camera_id / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Flux non disponible (camera hors ligne ?)")
    media_type = _MIME_TYPES.get(path.suffix, "application/octet-stream")
    headers = {"Cache-Control": "no-store"}
    return FileResponse(path, media_type=media_type, headers=headers)


@router.get("/{camera_id}/snapshot.jpg")
async def get_snapshot(
    camera_id: str,
    store: CameraStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
):
    _require_camera(camera_id, store)
    hls_dir = settings.hls_dir / camera_id
    segments = sorted(hls_dir.glob("seg_*.ts"))
    if not segments:
        raise HTTPException(status_code=404, detail="Aucune image disponible (camera hors ligne ?)")
    latest = segments[-1]
    proc = await asyncio.create_subprocess_exec(
        settings.ffmpeg_binary, "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-sseof", "-1", "-i", str(latest),
        "-frames:v", "1", "-q:v", "4", "-f", "image2", "pipe:1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    data, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
    if not data:
        raise HTTPException(status_code=500, detail="Impossible de generer la miniature")
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/{camera_id}/recordings")
def list_recordings(
    camera_id: str,
    date: str | None = None,
    store: CameraStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
):
    _require_camera(camera_id, store)
    rec_dir = settings.recordings_dir / camera_id
    if not rec_dir.exists():
        return []
    items = []
    for f in rec_dir.glob("*.mp4"):
        if not _RECORDING_NAME_RE.match(f.name):
            continue
        file_date = f.name[:10]
        if date and file_date != date:
            continue
        try:
            stat = f.stat()
        except OSError:
            continue
        items.append({
            "filename": f.name,
            "date": file_date,
            "time": f.name[11:19].replace("-", ":"),
            "size_bytes": stat.st_size,
            "modified_at": stat.st_mtime,
        })
    items.sort(key=lambda i: i["filename"])
    return items


def _resolve_recording_path(settings: Settings, camera_id: str, filename: str) -> Path:
    if not _RECORDING_NAME_RE.match(filename):
        raise HTTPException(status_code=400, detail="Nom de fichier invalide")
    rec_dir = (settings.recordings_dir / camera_id).resolve()
    path = (rec_dir / filename).resolve()
    if rec_dir not in path.parents:
        raise HTTPException(status_code=400, detail="Chemin invalide")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Enregistrement introuvable")
    return path


@router.get("/{camera_id}/recordings/{filename}")
def get_recording(
    camera_id: str,
    filename: str,
    store: CameraStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
):
    _require_camera(camera_id, store)
    path = _resolve_recording_path(settings, camera_id, filename)
    return FileResponse(path, media_type="video/mp4", filename=filename)


@router.delete("/{camera_id}/recordings/{filename}", status_code=204)
def delete_recording(
    camera_id: str,
    filename: str,
    store: CameraStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
):
    _require_camera(camera_id, store)
    path = _resolve_recording_path(settings, camera_id, filename)
    path.unlink()
    return None
