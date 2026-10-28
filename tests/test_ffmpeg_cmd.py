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


def test_live_bitrate_cap_forces_reencode_even_when_copy_capable(tmp_path: Path):
    cam = _camera(live_max_bitrate_kbps=800)
    cmd = build_live_cmd("ffmpeg", cam, tmp_path, hls_segment_seconds=2, hls_list_size=6)
    assert "copy" not in cmd  # forced re-encode, not stream copy
    assert "-b:v" in cmd
    assert cmd[cmd.index("-b:v") + 1] == "800k"
    assert "-maxrate" in cmd
    assert "-bufsize" in cmd


def test_live_scale_forces_reencode_and_adds_vf(tmp_path: Path):
    cam = _camera(live_scale="640x360")
    cmd = build_live_cmd("ffmpeg", cam, tmp_path, hls_segment_seconds=2, hls_list_size=6)
    assert "-vf" in cmd
    assert cmd[cmd.index("-vf") + 1] == "scale=640:360"


def test_live_without_cap_still_stream_copies_rtsp(tmp_path: Path):
    cmd = build_live_cmd("ffmpeg", _camera(), tmp_path, hls_segment_seconds=2, hls_list_size=6)
    assert "-c:v" in cmd and "copy" in cmd
    assert "-b:v" not in cmd


def test_record_leg_ignores_live_bandwidth_caps(tmp_path: Path):
    cam = _camera(live_max_bitrate_kbps=800, live_scale="640x360")
    cmd = build_record_cmd("ffmpeg", cam, tmp_path, segment_seconds=600)
    assert "-c" in cmd and "copy" in cmd  # recording stays full quality/stream-copy
    assert "-b:v" not in cmd
    assert "-vf" not in cmd


def test_rtmp_source_stream_copies(tmp_path: Path):
    cam = _camera(source_type=SourceType.rtmp, url="rtmp://x/live/stream1")
    cmd = build_record_cmd("ffmpeg", cam, tmp_path, segment_seconds=600)
    assert "rtmp://x/live/stream1" in cmd
    assert "-c" in cmd and "copy" in cmd
    assert "0:a:0?" in cmd


def test_srt_source_stream_copies(tmp_path: Path):
    cam = _camera(source_type=SourceType.srt, url="srt://x:9000?streamid=cam1")
    cmd = build_record_cmd("ffmpeg", cam, tmp_path, segment_seconds=600)
    assert "srt://x:9000?streamid=cam1" in cmd
    assert "-c" in cmd and "copy" in cmd


def test_srt_live_leg_is_video_only_and_copy(tmp_path: Path):
    cam = _camera(source_type=SourceType.srt, url="srt://x:9000")
    cmd = build_live_cmd("ffmpeg", cam, tmp_path, hls_segment_seconds=2, hls_list_size=6)
    assert "-c:v" in cmd and "copy" in cmd
    assert "0:a" not in " ".join(cmd)


def test_hw_encoder_used_when_resolved_and_reencode_needed(tmp_path: Path):
    cam = _camera(live_max_bitrate_kbps=800)
    cmd = build_live_cmd(
        "ffmpeg", cam, tmp_path, hls_segment_seconds=2, hls_list_size=6, hw_encoder="h264_v4l2m2m"
    )
    assert "h264_v4l2m2m" in cmd
    assert "libx264" not in cmd
    # Not supported by h264_v4l2m2m (a fixed hardware pipeline, not
    # libavcodec's software rate-distortion options) - must not be sent.
    assert "-preset" not in cmd
    assert "-tune" not in cmd
    assert cmd[cmd.index("-b:v") + 1] == "800k"


def test_hw_encoder_gets_a_default_bitrate_when_no_cap_set(tmp_path: Path):
    cam = _camera(source_type=SourceType.test, url="test:pattern")
    cmd = build_record_cmd("ffmpeg", cam, tmp_path, segment_seconds=600, hw_encoder="h264_v4l2m2m")
    assert "h264_v4l2m2m" in cmd
    assert "-b:v" in cmd  # the hw encoder's own low default would otherwise apply


def test_hw_encoder_not_used_for_a_plain_stream_copy(tmp_path: Path):
    # Still copy_ok with no cap/scale set - hw_encoder is irrelevant here,
    # it should never appear even though one was resolved at startup.
    cmd = build_live_cmd(
        "ffmpeg", _camera(), tmp_path, hls_segment_seconds=2, hls_list_size=6, hw_encoder="h264_v4l2m2m"
    )
    assert "h264_v4l2m2m" not in cmd
    assert "-c:v" in cmd and "copy" in cmd


def test_no_hw_encoder_falls_back_to_libx264(tmp_path: Path):
    cam = _camera(live_max_bitrate_kbps=800)
    cmd = build_live_cmd(
        "ffmpeg", cam, tmp_path, hls_segment_seconds=2, hls_list_size=6, hw_encoder=None
    )
    assert "libx264" in cmd
    assert "h264_v4l2m2m" not in cmd
