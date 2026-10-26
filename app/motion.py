"""Motion detection.

Deliberately reads from the camera's own live HLS segments already being
written to disk by the live leg (same trick as the snapshot endpoint)
instead of opening a third connection to the camera: it costs nothing
extra on the camera or the network.

Detection itself is a small hand-rolled grayscale frame-diff rather than
pulling in OpenCV/numpy, in keeping with the rest of this codebase (the
hand-rolled ONVIF/WS-Discovery clients, the stdlib-only PNG icons): ffmpeg
downscales a frame to DETECT_W x DETECT_H 8-bit grayscale, and comparing
two of those is a couple thousand byte subtractions - fast enough in
plain Python at the cadence this runs.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import Settings
from app.models import MOTION_GRID_COLS, MOTION_GRID_ROWS, Camera
from app.notifier import Notifier
from app.store import CameraStore

logger = logging.getLogger("nvr.motion")

DETECT_W = 48
DETECT_H = 27
_FRAME_BYTES = DETECT_W * DETECT_H

# Per-pixel gray-level delta (0-255) below which a pixel isn't counted as
# "changed" at all - filters out sensor/encoder noise on a static scene.
_PIXEL_NOISE_FLOOR = 22

# sensitivity 0 -> need this fraction of (non-masked) pixels to change;
# sensitivity 100 -> need only this much. Linear in between.
_TRIGGER_RATIO_AT_MIN_SENSITIVITY = 0.22
_TRIGGER_RATIO_AT_MAX_SENSITIVITY = 0.015


def sensitivity_to_trigger_ratio(sensitivity: int) -> float:
    sensitivity = max(0, min(100, sensitivity))
    span = _TRIGGER_RATIO_AT_MIN_SENSITIVITY - _TRIGGER_RATIO_AT_MAX_SENSITIVITY
    return _TRIGGER_RATIO_AT_MIN_SENSITIVITY - span * (sensitivity / 100)


def mask_grid_to_pixels(mask_grid: list[bool], mask_mode: str = "exclude") -> Optional[bytearray]:
    """Expands the coarse MOTION_GRID_COLS x MOTION_GRID_ROWS UI grid to a
    DETECT_W x DETECT_H boolean-per-pixel mask (1 = excluded from
    detection), or None if nothing ends up excluded (the common
    "exclude" case with no cell selected - skip masking work entirely).

    mask_mode="exclude" (default): a selected cell is excluded, the rest
    of the frame is monitored - a "zone a ignorer".
    mask_mode="include": a selected cell is the only part monitored, the
    rest is excluded - a "zone a surveiller". With nothing selected, every
    pixel ends up excluded (monitors nothing) - a real configuration, not
    a fallback to "monitor everything".
    """
    if mask_mode == "exclude" and not any(mask_grid):
        return None
    pixels = bytearray(_FRAME_BYTES)
    for y in range(DETECT_H):
        grid_row = y * MOTION_GRID_ROWS // DETECT_H
        for x in range(DETECT_W):
            grid_col = x * MOTION_GRID_COLS // DETECT_W
            selected = bool(mask_grid) and mask_grid[grid_row * MOTION_GRID_COLS + grid_col]
            excluded = not selected if mask_mode == "include" else selected
            if excluded:
                pixels[y * DETECT_W + x] = 1
    return pixels


def compute_changed_ratio(prev: bytes, curr: bytes, mask_pixels: Optional[bytearray]) -> float:
    changed = 0
    total = 0
    for i in range(_FRAME_BYTES):
        if mask_pixels is not None and mask_pixels[i]:
            continue
        total += 1
        delta = prev[i] - curr[i]
        if delta < 0:
            delta = -delta
        if delta >= _PIXEL_NOISE_FLOOR:
            changed += 1
    if total == 0:
        return 0.0
    return changed / total


async def extract_gray_frame(ffmpeg_bin: str, segment_path: Path) -> Optional[bytes]:
    """Grabs the last frame of `segment_path` as raw DETECT_W x DETECT_H
    8-bit grayscale pixels (exactly _FRAME_BYTES bytes), or None on failure.

    Uses `-vf reverse` + `-frames:v 1` rather than `-sseof -1`: mpegts HLS
    segments (as ffmpeg itself writes them) report a nonzero stream start
    time, which throws off EOF-relative seeking and can silently produce
    zero output frames. Reversing and taking the first frame sidesteps
    seeking entirely - cheap here since a single HLS segment is only a
    couple of seconds of video."""
    cmd = [
        ffmpeg_bin, "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", str(segment_path),
        "-vf", f"reverse,scale={DETECT_W}:{DETECT_H}",
        "-frames:v", "1", "-pix_fmt", "gray", "-f", "rawvideo", "pipe:1",
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        data, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
    except (FileNotFoundError, asyncio.TimeoutError):
        return None
    if len(data) != _FRAME_BYTES:
        return None
    return data


@dataclass
class MotionState:
    active: bool = False
    last_ratio: float = 0.0
    last_checked_at: Optional[str] = None
    last_motion_at: Optional[str] = None


@dataclass
class _CameraMotion:
    prev_frame: Optional[bytes] = None
    state: MotionState = field(default_factory=MotionState)
    # monotonic clock, for the cooldown - time.monotonic()'s reference
    # point is unspecified (could be near 0 on a freshly booted host), so
    # a 0.0 "never fired yet" sentinel could wrongly look recent and
    # suppress the very first event; -inf can't ever do that.
    last_event_at: float = float("-inf")


class MotionRegistry:
    """In-memory current motion state per camera, plus a lightweight
    append-only per-camera event log on disk (data_dir/motion/<id>.jsonl)
    so recent motion history survives a restart."""

    def __init__(self, motion_dir: Path):
        self._motion_dir = motion_dir
        self._lock = threading.RLock()
        self._cameras: dict[str, _CameraMotion] = {}

    def _get(self, camera_id: str) -> _CameraMotion:
        with self._lock:
            return self._cameras.setdefault(camera_id, _CameraMotion())

    def state(self, camera_id: str) -> MotionState:
        return self._get(camera_id).state

    def invalidate(self, camera_id: str) -> None:
        with self._lock:
            self._cameras.pop(camera_id, None)

    def recent_events(self, camera_id: str, limit: int = 20) -> list[dict]:
        path = self._motion_dir / f"{camera_id}.jsonl"
        if not path.exists():
            return []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        events = []
        for line in lines[-limit:]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        events.reverse()
        return events

    def _append_event(self, camera_id: str, ratio: float) -> None:
        self._motion_dir.mkdir(parents=True, exist_ok=True)
        path = self._motion_dir / f"{camera_id}.jsonl"
        entry = {"at": datetime.now(timezone.utc).isoformat(), "ratio": round(ratio, 4)}
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError:
            logger.exception("motion: failed to append event for %s", camera_id)

    def observe(self, camera_id: str, ratio: float, triggered: bool, cooldown_seconds: float) -> bool:
        """Returns True iff a new motion *event* was actually recorded (i.e.
        triggered, and not suppressed by the per-camera cooldown) - the
        signal callers use to fire a one-shot notification per event
        rather than on every single triggered check."""
        cam = self._get(camera_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        cam.state.last_ratio = ratio
        cam.state.last_checked_at = now_iso
        cam.state.active = triggered
        if not triggered:
            return False
        cam.state.last_motion_at = now_iso
        now_mono = time.monotonic()
        if now_mono - cam.last_event_at >= cooldown_seconds:
            cam.last_event_at = now_mono
            self._append_event(camera_id, ratio)
            return True
        return False


async def process_camera(
    settings: Settings, camera: Camera, registry: MotionRegistry, notifier: Optional[Notifier] = None
) -> None:
    if not camera.motion_enabled:
        return
    hls_dir = settings.hls_dir / camera.id
    segments = sorted(hls_dir.glob("seg_*.ts"))
    if not segments:
        return
    frame = await extract_gray_frame(settings.ffmpeg_binary, segments[-1])
    if frame is None:
        return

    cam_state = registry._get(camera.id)  # noqa: SLF001 - same module, avoid a public getter+setter pair
    mask_pixels = mask_grid_to_pixels(camera.motion_mask_grid, camera.motion_mask_mode)
    if cam_state.prev_frame is not None:
        ratio = compute_changed_ratio(cam_state.prev_frame, frame, mask_pixels)
        triggered = ratio >= sensitivity_to_trigger_ratio(camera.motion_sensitivity)
        new_event = registry.observe(camera.id, ratio, triggered, settings.motion_event_cooldown_seconds)
        if new_event and notifier is not None:
            await notifier.notify_motion(camera.id, camera.name)
    cam_state.prev_frame = frame


async def motion_loop(
    settings: Settings,
    store: CameraStore,
    registry: MotionRegistry,
    stop_event: asyncio.Event,
    notifier: Optional[Notifier] = None,
) -> None:
    while not stop_event.is_set():
        try:
            for camera in store.list():
                if camera.enabled and camera.motion_enabled:
                    await process_camera(settings, camera, registry, notifier)
        except Exception:  # pragma: no cover - defensive
            logger.exception("motion: unexpected error in loop")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.motion_check_interval_seconds)
        except asyncio.TimeoutError:
            pass
