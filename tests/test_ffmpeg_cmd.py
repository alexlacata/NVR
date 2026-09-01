from pathlib import Path

from app.ffmpeg_cmd import build_live_cmd, build_record_cmd
from app.models import Camera, SourceType


def _camera(**kwargs):
    defaults = dict(id="cam1", name="Cam 1", source_type=SourceType.rtsp, url="rtsp://x/1")
    defaults.update(kwargs)
    return Camera(**defaults)


def test_record_rtsp_uses_stream_copy_and_keeps_audio(tmp_path: Path):
    cmd = build_record_cmd("ffmpeg", _camera(), tmp_path, segment_seconds=600)
    assert "-c" in cmd and "copy" in cmd
    assert "0:v:0" in cmd
    assert "0:a:0?" in cmd  # optional audio map: won't fail if camera has none


def test_live_rtsp_is_video_only(tmp_path: Path):
    cmd = build_live_cmd("ffmpeg", _camera(), tmp_path, hls_segment_seconds=2, hls_list_size=6)
    assert "0:a:0?" not in cmd
    assert "0:a" not in " ".join(cmd)
    assert "-c:v" in cmd and "copy" in cmd


def test_live_uses_live_url_when_set(tmp_path: Path):
    cam = _camera(live_url="rtsp://x/substream")
    cmd = build_live_cmd("ffmpeg", cam, tmp_path, hls_segment_seconds=2, hls_list_size=6)
    assert "rtsp://x/substream" in cmd
    assert "rtsp://x/1" not in cmd


def test_record_still_uses_main_url_when_live_url_set(tmp_path: Path):
    cam = _camera(live_url="rtsp://x/substream")
    cmd = build_record_cmd("ffmpeg", cam, tmp_path, segment_seconds=600)
    assert "rtsp://x/1" in cmd
    assert "rtsp://x/substream" not in cmd


def test_test_source_generates_synthetic_lavfi_input(tmp_path: Path):
    cam = _camera(source_type=SourceType.test, url="test:pattern")
    cmd = build_record_cmd("ffmpeg", cam, tmp_path, segment_seconds=600)
    assert "lavfi" in cmd
    assert "-c:v" in cmd and "libx264" in cmd  # re-encoded, not copied
