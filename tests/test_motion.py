import asyncio
import shutil
from pathlib import Path

import pytest

from app.models import MOTION_GRID_CELLS
from app.motion import (
    DETECT_H,
    DETECT_W,
    MotionRegistry,
    compute_changed_ratio,
    extract_gray_frame,
    mask_grid_to_pixels,
    process_camera,
    sensitivity_to_trigger_ratio,
)


def test_sensitivity_to_trigger_ratio_is_monotonically_decreasing():
    # higher sensitivity -> smaller changed-pixel ratio needed to trigger
    ratios = [sensitivity_to_trigger_ratio(s) for s in (0, 25, 50, 75, 100)]
    assert ratios == sorted(ratios, reverse=True)
    assert ratios[0] > ratios[-1]
    for r in ratios:
        assert 0 < r < 1


def test_mask_grid_to_pixels_none_when_empty_or_all_false():
    assert mask_grid_to_pixels([]) is None
    assert mask_grid_to_pixels([False] * MOTION_GRID_CELLS) is None


def test_mask_grid_to_pixels_masks_the_right_pixels():
    grid = [False] * MOTION_GRID_CELLS
    grid[0] = True  # top-left grid cell
    pixels = mask_grid_to_pixels(grid)
    assert pixels is not None
    assert len(pixels) == DETECT_W * DETECT_H
    assert pixels[0] == 1  # top-left pixel is inside the masked cell
    assert pixels[DETECT_W - 1] == 0  # top-right pixel is not (grid is 8 wide)


def test_compute_changed_ratio_identical_frames_is_zero():
    frame = bytes([100]) * (DETECT_W * DETECT_H)
    assert compute_changed_ratio(frame, frame, None) == 0.0


def test_compute_changed_ratio_fully_different_frames_is_one():
    black = bytes([0]) * (DETECT_W * DETECT_H)
    white = bytes([255]) * (DETECT_W * DETECT_H)
    assert compute_changed_ratio(black, white, None) == 1.0


def test_compute_changed_ratio_below_noise_floor_does_not_count():
    a = bytes([100]) * (DETECT_W * DETECT_H)
    b = bytes([105]) * (DETECT_W * DETECT_H)  # delta 5, well under the noise floor
    assert compute_changed_ratio(a, b, None) == 0.0


def test_compute_changed_ratio_masked_pixels_are_excluded():
    black = bytearray([0]) * (DETECT_W * DETECT_H)
    white = bytearray([255]) * (DETECT_W * DETECT_H)
    mask = bytearray([1]) * (DETECT_W * DETECT_H)  # everything masked
    assert compute_changed_ratio(bytes(black), bytes(white), mask) == 0.0


def test_motion_registry_observe_updates_state_and_cooldown(tmp_path):
    registry = MotionRegistry(tmp_path)
    registry.observe("cam1", ratio=0.5, triggered=True, cooldown_seconds=9999)
    state = registry.state("cam1")
    assert state.active is True
    assert state.last_ratio == 0.5
    assert state.last_motion_at is not None
    events = registry.recent_events("cam1")
    assert len(events) == 1

    # a second trigger within the cooldown window should not add another event
    registry.observe("cam1", ratio=0.6, triggered=True, cooldown_seconds=9999)
    assert len(registry.recent_events("cam1")) == 1

    # not triggered -> active flips false, no new event, but last_motion_at is kept
    registry.observe("cam1", ratio=0.01, triggered=False, cooldown_seconds=9999)
    state = registry.state("cam1")
    assert state.active is False
    assert state.last_motion_at is not None
    assert len(registry.recent_events("cam1")) == 1


def test_motion_registry_invalidate_clears_in_memory_state(tmp_path):
    registry = MotionRegistry(tmp_path)
    registry.observe("cam1", ratio=0.5, triggered=True, cooldown_seconds=9999)
    registry.invalidate("cam1")
    assert registry.state("cam1").active is False  # fresh default state


pytestmark_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


async def _make_solid_segment(path: Path, color: str, duration: int = 2):
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"color=c={color}:size=320x180:rate=5:duration={duration}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(path),
    ]
    proc = await asyncio.create_subprocess_exec(*cmd)
    await proc.wait()


@pytestmark_ffmpeg
@pytest.mark.asyncio
async def test_extract_gray_frame_returns_expected_size(tmp_path):
    segment = tmp_path / "seg_000.ts"
    await _make_solid_segment(segment, "gray")
    frame = await extract_gray_frame("ffmpeg", segment)
    assert frame is not None
    assert len(frame) == DETECT_W * DETECT_H


@pytestmark_ffmpeg
@pytest.mark.asyncio
async def test_extract_gray_frame_missing_file_returns_none(tmp_path):
    frame = await extract_gray_frame("ffmpeg", tmp_path / "does-not-exist.ts")
    assert frame is None


class FakeMotionSettings:
    def __init__(self, base: Path):
        self.hls_dir = base / "hls"
        self.ffmpeg_binary = "ffmpeg"
        self.motion_event_cooldown_seconds = 9999


class FakeMotionCamera:
    def __init__(self, id="cam1", name="Cam 1", motion_enabled=True, motion_sensitivity=90, motion_mask_grid=None):
        self.id = id
        self.name = name
        self.motion_enabled = motion_enabled
        self.motion_sensitivity = motion_sensitivity
        self.motion_mask_grid = motion_mask_grid or []


class FakeNotifier:
    def __init__(self):
        self.motion_calls = []

    async def notify_motion(self, camera_id, camera_name):
        self.motion_calls.append((camera_id, camera_name))


@pytestmark_ffmpeg
@pytest.mark.asyncio
async def test_process_camera_detects_change_between_black_and_white(tmp_path):
    settings = FakeMotionSettings(tmp_path)
    hls_dir = settings.hls_dir / "cam1"
    hls_dir.mkdir(parents=True)
    registry = MotionRegistry(tmp_path / "motion")
    camera = FakeMotionCamera(motion_sensitivity=90)  # low trigger threshold

    await _make_solid_segment(hls_dir / "seg_000.ts", "black")
    await process_camera(settings, camera, registry)
    assert registry.state("cam1").last_checked_at is None  # first frame only seeds prev_frame

    await _make_solid_segment(hls_dir / "seg_001.ts", "white")
    await process_camera(settings, camera, registry)
    state = registry.state("cam1")
    assert state.last_checked_at is not None
    assert state.last_ratio > 0.9
    assert state.active is True


@pytestmark_ffmpeg
@pytest.mark.asyncio
async def test_process_camera_no_change_does_not_trigger(tmp_path):
    settings = FakeMotionSettings(tmp_path)
    hls_dir = settings.hls_dir / "cam1"
    hls_dir.mkdir(parents=True)
    registry = MotionRegistry(tmp_path / "motion")
    camera = FakeMotionCamera(motion_sensitivity=90)

    await _make_solid_segment(hls_dir / "seg_000.ts", "gray")
    await process_camera(settings, camera, registry)
    await _make_solid_segment(hls_dir / "seg_001.ts", "gray")
    await process_camera(settings, camera, registry)

    state = registry.state("cam1")
    assert state.last_ratio == 0.0
    assert state.active is False


@pytestmark_ffmpeg
@pytest.mark.asyncio
async def test_process_camera_notifies_on_new_motion_event(tmp_path):
    settings = FakeMotionSettings(tmp_path)
    hls_dir = settings.hls_dir / "cam1"
    hls_dir.mkdir(parents=True)
    registry = MotionRegistry(tmp_path / "motion")
    camera = FakeMotionCamera(motion_sensitivity=90, name="Garage")
    notifier = FakeNotifier()

    await _make_solid_segment(hls_dir / "seg_000.ts", "black")
    await process_camera(settings, camera, registry, notifier)
    assert notifier.motion_calls == []  # first frame only seeds prev_frame, no event yet

    await _make_solid_segment(hls_dir / "seg_001.ts", "white")
    await process_camera(settings, camera, registry, notifier)
    assert notifier.motion_calls == [("cam1", "Garage")]


@pytest.mark.asyncio
async def test_process_camera_skips_when_motion_disabled(tmp_path):
    settings = FakeMotionSettings(tmp_path)
    registry = MotionRegistry(tmp_path / "motion")
    camera = FakeMotionCamera(motion_enabled=False)
    await process_camera(settings, camera, registry)
    assert registry.state("cam1").last_checked_at is None


@pytest.mark.asyncio
async def test_process_camera_skips_when_no_hls_segments(tmp_path):
    settings = FakeMotionSettings(tmp_path)
    registry = MotionRegistry(tmp_path / "motion")
    camera = FakeMotionCamera()
    await process_camera(settings, camera, registry)
    assert registry.state("cam1").last_checked_at is None
