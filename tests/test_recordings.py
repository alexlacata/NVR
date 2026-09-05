import hashlib
from datetime import datetime
from pathlib import Path

from app.recordings import list_recording_segments, parse_recording_start, sha256_of_file


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


def test_sha256_of_file_matches_hashlib(tmp_path: Path):
    f = tmp_path / "rec.mp4"
    content = b"some fake recording bytes" * 10000  # bigger than one hash chunk
    f.write_bytes(content)
    assert sha256_of_file(f) == hashlib.sha256(content).hexdigest()


def test_sha256_of_file_empty_file(tmp_path: Path):
    f = tmp_path / "empty.mp4"
    f.write_bytes(b"")
    assert sha256_of_file(f) == hashlib.sha256(b"").hexdigest()
