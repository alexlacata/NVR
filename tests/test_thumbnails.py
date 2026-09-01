import shutil
from datetime import datetime
from pathlib import Path

import pytest

from app.thumbnails import extract_segment_thumbnails, process_camera

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


async def _make_test_segment(path: Path, duration: int = 6):
    import asyncio
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size=320x240:rate=10:duration={duration}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(path),
    ]
    proc = await asyncio.create_subprocess_exec(*cmd)
    await proc.wait()


@pytest.mark.asyncio
async def test_extract_segment_thumbnails_produces_timestamped_files(tmp_path):
    segment = tmp_path / "segment.mp4"
    await _make_test_segment(segment, duration=6)
    out_dir = tmp_path / "thumbs"

    start = datetime(2026, 9, 1, 8, 0, 0)
    count = await extract_segment_thumbnails("ffmpeg", segment, start, out_dir, interval_seconds=2)

    assert count >= 2
    names = sorted(p.name for p in out_dir.glob("*.jpg"))
    assert "2026-09-01_08-00-00.jpg" in names
    assert "2026-09-01_08-00-02.jpg" in names
    assert not list(out_dir.glob(".tmp-*"))  # temp files cleaned up


@pytest.mark.asyncio
async def test_extract_segment_thumbnails_skips_already_processed(tmp_path):
    segment = tmp_path / "segment.mp4"
    await _make_test_segment(segment, duration=4)
    out_dir = tmp_path / "thumbs"
    out_dir.mkdir()
    start = datetime(2026, 9, 1, 8, 0, 0)
    (out_dir / "2026-09-01_08-00-00.jpg").write_bytes(b"already-here")

    count = await extract_segment_thumbnails("ffmpeg", segment, start, out_dir, interval_seconds=2)

    # the pre-existing marker file must not be clobbered
    assert (out_dir / "2026-09-01_08-00-00.jpg").read_bytes() == b"already-here"
    assert count >= 1  # later frames in the segment still get written


class FakeSettings:
    def __init__(self, base: Path, ffmpeg_binary="ffmpeg", thumbnail_interval_seconds=2):
        self.recordings_dir = base / "recordings"
        self.thumbnails_dir = base / "thumbnails"
        self.ffmpeg_binary = ffmpeg_binary
        self.thumbnail_interval_seconds = thumbnail_interval_seconds


class FakeCamera:
    def __init__(self, id="cam1", enabled=True, record=True, thumbnail_interval_seconds=None):
        self.id = id
        self.enabled = enabled
        self.record = record
        self.thumbnail_interval_seconds = thumbnail_interval_seconds


@pytest.mark.asyncio
async def test_process_camera_skips_the_currently_open_segment(tmp_path):
    settings = FakeSettings(tmp_path)
    cam_dir = settings.recordings_dir / "cam1"
    cam_dir.mkdir(parents=True)
    seg1 = cam_dir / "2026-09-01_08-00-00.mp4"
    seg2 = cam_dir / "2026-09-01_08-00-10.mp4"  # the "currently open" one, newest start time
    await _make_test_segment(seg1, duration=4)
    await _make_test_segment(seg2, duration=4)

    await process_camera(settings, FakeCamera())

    thumbs_dir = settings.thumbnails_dir / "cam1"
    thumb_names = {p.name for p in thumbs_dir.glob("*.jpg")} if thumbs_dir.exists() else set()
    assert any(n.startswith("2026-09-01_08-00-00") for n in thumb_names)
    assert not any(n.startswith("2026-09-01_08-00-10") for n in thumb_names)


@pytest.mark.asyncio
async def test_process_camera_handles_segments_closer_together_than_interval(tmp_path):
    # A camera that drops and reconnects mid-segment can start a new segment
    # well before the previous one's nominal duration elapsed. Two segments
    # whose start times are closer together than the thumbnail interval
    # must still each get their own thumbnails processed, not have the
    # second look "already done" because of a filename collision.
    settings = FakeSettings(tmp_path, thumbnail_interval_seconds=2)
    cam_dir = settings.recordings_dir / "cam1"
    cam_dir.mkdir(parents=True)
    seg1 = cam_dir / "2026-09-01_08-00-00.mp4"
    seg2 = cam_dir / "2026-09-01_08-00-01.mp4"  # only 1s after seg1's start
    seg3 = cam_dir / "2026-09-01_08-00-02.mp4"  # the "currently open" one
    await _make_test_segment(seg1, duration=6)
    await _make_test_segment(seg2, duration=6)
    await _make_test_segment(seg3, duration=2)

    await process_camera(settings, FakeCamera())

    thumbs_dir = settings.thumbnails_dir / "cam1"
    assert (thumbs_dir / ".done-2026-09-01_08-00-00").exists()
    assert (thumbs_dir / ".done-2026-09-01_08-00-01").exists()
    assert not (thumbs_dir / ".done-2026-09-01_08-00-02").exists()  # still open, skipped


@pytest.mark.asyncio
async def test_process_camera_noop_with_single_segment(tmp_path):
    settings = FakeSettings(tmp_path)
    cam_dir = settings.recordings_dir / "cam1"
    cam_dir.mkdir(parents=True)
    await _make_test_segment(cam_dir / "2026-09-01_08-00-00.mp4", duration=3)

    await process_camera(settings, FakeCamera())

    assert not (settings.thumbnails_dir / "cam1").exists()
