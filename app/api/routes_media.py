from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse

from app.audit_log import AuditLog
from app.config import Settings
from app.deps import (
    get_audit_log,
    get_settings,
    get_store,
    require_auth,
    require_recordings_delete,
    require_recordings_download,
)
from app.models import User
from app.recordings import RECORDING_NAME_RE, list_recording_segments, sha256_of_file
from app.store import CameraNotFound, CameraStore

router = APIRouter(prefix="/api/cameras", tags=["media"], dependencies=[Depends(require_auth)])

_HLS_NAME_RE = re.compile(r"^(stream\.m3u8|seg_\d+\.ts)$")
_THUMB_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.jpg$")

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
        # `-vf reverse` + `-frames:v 1` instead of `-sseof -1`: an HLS
        # segment's mpegts container reports a nonzero stream start time,
        # which throws off EOF-relative seeking and can silently yield
        # zero output frames on some ffmpeg builds. Reversing and taking
        # the first frame sidesteps seeking entirely - cheap here since a
        # single HLS segment is only a couple of seconds of video.
        settings.ffmpeg_binary, "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", str(latest),
        "-vf", "reverse", "-frames:v", "1", "-q:v", "4", "-f", "image2", "pipe:1",
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
        if not RECORDING_NAME_RE.match(f.name):
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


@router.get("/{camera_id}/recordings/at")
def find_recording_at(
    camera_id: str,
    ts: str,
    store: CameraStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
):
    """Given an ISO 8601 timestamp, find which recording segment covers it
    and the offset (seconds) to seek to within that file — used by the
    timeline and thumbnail strip to jump playback to an exact point in
    time, without the client needing to know the segment length."""
    _require_camera(camera_id, store)
    try:
        target = datetime.fromisoformat(ts)
    except ValueError:
        raise HTTPException(status_code=400, detail="Horodatage invalide (attendu au format ISO 8601)")

    segments = list_recording_segments(settings.recordings_dir / camera_id)
    if not segments:
        raise HTTPException(status_code=404, detail="Aucun enregistrement pour cette camera")

    chosen = None
    for start, path in segments:
        if start <= target:
            chosen = (start, path)
        else:
            break
    if chosen is None:
        chosen = segments[0]  # target is before anything recorded: snap to the earliest segment
    start, path = chosen
    offset = max(0.0, (target - start).total_seconds())
    return {"filename": path.name, "offset_seconds": offset}


@router.get("/{camera_id}/thumbnails")
def list_thumbnails(
    camera_id: str,
    date: str | None = None,
    store: CameraStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
):
    _require_camera(camera_id, store)
    thumb_dir = settings.thumbnails_dir / camera_id
    if not thumb_dir.exists():
        return []
    items = []
    for f in thumb_dir.glob("*.jpg"):
        if not _THUMB_NAME_RE.match(f.name):
            continue
        file_date = f.name[:10]
        if date and file_date != date:
            continue
        items.append({
            "filename": f.name,
            "date": file_date,
            "time": f.name[11:19].replace("-", ":"),
        })
    items.sort(key=lambda i: i["filename"])
    return items


@router.get("/{camera_id}/thumbnails/{filename}")
def get_thumbnail(
    camera_id: str,
    filename: str,
    store: CameraStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
):
    _require_camera(camera_id, store)
    if not _THUMB_NAME_RE.match(filename):
        raise HTTPException(status_code=400, detail="Nom de fichier invalide")
    thumb_dir = (settings.thumbnails_dir / camera_id).resolve()
    path = (thumb_dir / filename).resolve()
    if thumb_dir not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Vignette introuvable")
    # Thumbnails are never modified after creation, so they can be cached
    # aggressively by the browser.
    headers = {"Cache-Control": "public, max-age=31536000, immutable"}
    return FileResponse(path, media_type="image/jpeg", headers=headers)


def _resolve_recording_path(settings: Settings, camera_id: str, filename: str) -> Path:
    if not RECORDING_NAME_RE.match(filename):
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
    user: User = Depends(require_auth),
    audit_log: AuditLog = Depends(get_audit_log),
):
    _require_camera(camera_id, store)
    path = _resolve_recording_path(settings, camera_id, filename)
    audit_log.record(user.username, "view", camera_id, filename, dedupe_seconds=60)
    return FileResponse(path, media_type="video/mp4", filename=filename)


@router.get(
    "/{camera_id}/recordings/{filename}/download",
    dependencies=[Depends(require_recordings_download)],
)
def download_recording(
    camera_id: str,
    filename: str,
    store: CameraStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
    user: User = Depends(require_auth),
    audit_log: AuditLog = Depends(get_audit_log),
):
    """Separate from get_recording (used for inline <video> playback, which
    stays open to any authenticated user): this is the one gated behind the
    `recordings_download` permission, so an admin can let a viewer watch
    recordings without letting them save a copy to their device - handy to
    keep download off for accounts that mostly connect over a metered 4G
    link."""
    _require_camera(camera_id, store)
    path = _resolve_recording_path(settings, camera_id, filename)
    audit_log.record(user.username, "download", camera_id, filename)
    return FileResponse(path, media_type="video/mp4", filename=filename)


@router.get(
    "/{camera_id}/recordings/{filename}/checksum",
    dependencies=[Depends(require_recordings_download)],
)
def get_recording_checksum(
    camera_id: str,
    filename: str,
    store: CameraStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
):
    """SHA256 of a recording, computed on demand from the file currently on
    disk - for chain-of-custody purposes (prove a downloaded copy matches
    what the NVR actually holds). Gated behind the same permission as
    download, since checksumming only matters once you have a copy to
    verify against."""
    _require_camera(camera_id, store)
    path = _resolve_recording_path(settings, camera_id, filename)
    return {
        "filename": filename,
        "sha256": sha256_of_file(path),
        "size_bytes": path.stat().st_size,
    }


@router.delete("/{camera_id}/recordings/{filename}", status_code=204, dependencies=[Depends(require_recordings_delete)])
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
