from datetime import datetime
from pathlib import Path

from app.recordings import list_recording_segments, parse_recording_start


def test_parse_recording_start_valid():
    dt = parse_recording_start("2026-09-01_08-30-05.mp4")
    assert dt == datetime(2026, 9, 1, 8, 30, 5)


def test_parse_recording_start_invalid_returns_none():
    assert parse_recording_start("not-a-segment.mp4") is None
    assert parse_recording_start("2026-09-01_08-30-05.jpg") is None


def test_list_recording_segments_sorted(tmp_path: Path):
    cam_dir = tmp_path / "cam1"
    cam_dir.mkdir()
    (cam_dir / "2026-09-01_09-00-00.mp4").write_bytes(b"0")
    (cam_dir / "2026-09-01_08-00-00.mp4").write_bytes(b"0")
    (cam_dir / "ignored.txt").write_bytes(b"0")

    segments = list_recording_segments(cam_dir)

    assert [p.name for _, p in segments] == ["2026-09-01_08-00-00.mp4", "2026-09-01_09-00-00.mp4"]
    assert segments[0][0] == datetime(2026, 9, 1, 8, 0, 0)


def test_list_recording_segments_missing_dir(tmp_path: Path):
    assert list_recording_segments(tmp_path / "nope") == []
