"""Extracts periodic thumbnails from finished recording segments, so the
web UI can offer a scrubbable timeline of what was recorded.

Deliberately reads from segment files already on disk rather than opening
a third live connection to the camera: it costs no extra bandwidth or
connection slot on the camera, and thumbnails are only ever produced for
footage that was actually recorded.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from pathlib import Path

from app.config import Settings
from app.recordings import list_recording_segments
from app.store import CameraStore

logger = logging.getLogger("nvr.thumbnails")


def _camera_interval(camera, settings: Settings) -> int:
    return camera.thumbnail_interval_seconds or settings.thumbnail_interval_seconds


def _thumbnail_name(dt) -> str:
    return dt.strftime("%Y-%m-%d_%H-%M-%S.jpg")


async def extract_segment_thumbnails(
    ffmpeg_bin: str,
    segment_path: Path,
    segment_start,
    out_dir: Path,
    interval_seconds: int,
) -> int:
    """Extract one frame every `interval_seconds` from `segment_path`,
    writing timestamped JPEGs into `out_dir`. Returns the number produced."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_pattern = out_dir / f".tmp-{segment_path.stem}-%06d.jpg"
    cmd = [
        ffmpeg_bin, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(segment_path),
        "-vf", f"fps=1/{interval_seconds}",
        "-q:v", "5",
        "-f", "image2",
        str(tmp_pattern),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning("thumbnails: ffmpeg failed on %s: %s", segment_path, stderr.decode("utf-8", "replace")[-400:])

    produced = sorted(out_dir.glob(f".tmp-{segment_path.stem}-*.jpg"))
    count = 0
    for i, tmp_file in enumerate(produced):
        ts = segment_start + timedelta(seconds=i * interval_seconds)
        final_path = out_dir / _thumbnail_name(ts)
        try:
            if final_path.exists():
                tmp_file.unlink()
            else:
                tmp_file.rename(final_path)
                count += 1
        except OSError:
            pass
    return count


def _done_marker(out_dir: Path, segment_path: Path) -> Path:
    # A dedicated marker keyed on the segment's own filename - not on a
    # derived thumbnail timestamp - so it can never collide with another
    # segment's output. Segments aren't always exactly `segment_seconds`
    # apart (a camera that drops and reconnects mid-segment starts a new,
    # shorter one right away), so two segments' timestamp-derived thumbnail
    # names could otherwise coincide and make a real segment look already
    # processed when it isn't.
    return out_dir / f".done-{segment_path.stem}"


async def process_camera(settings: Settings, camera) -> None:
    rec_dir = settings.recordings_dir / camera.id
    segments = list_recording_segments(rec_dir)
    if not segments:
        return
    # The most recently started segment may still be actively written by
    # ffmpeg; leave it alone until a newer one shows it has rotated out.
    finished = segments[:-1]
    if not finished:
        return

    out_dir = settings.thumbnails_dir / camera.id
    interval = _camera_interval(camera, settings)

    for start, path in finished:
        marker = _done_marker(out_dir, path)
        if marker.exists():
            continue
        try:
            await extract_segment_thumbnails(settings.ffmpeg_binary, path, start, out_dir, interval)
            out_dir.mkdir(parents=True, exist_ok=True)
            marker.touch()
        except FileNotFoundError:
            logger.error("thumbnails: ffmpeg binary not found (%s)", settings.ffmpeg_binary)
            return
        except Exception:  # pragma: no cover - defensive
            logger.exception("thumbnails: failed to process %s", path)


async def thumbnail_loop(settings: Settings, store: CameraStore, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            for camera in store.list():
                if camera.enabled and camera.record:
                    await process_camera(settings, camera)
        except Exception:  # pragma: no cover - defensive
            logger.exception("thumbnails: unexpected error in loop")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.thumbnail_check_interval_seconds)
        except asyncio.TimeoutError:
            pass
