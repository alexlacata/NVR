import pytest
from pydantic import ValidationError

from app.models import Camera, SourceType


def _base(**kwargs):
    defaults = dict(id="cam1", name="Cam 1", source_type=SourceType.rtsp, url="rtsp://x/1")
    defaults.update(kwargs)
    return defaults


def test_ptz_enabled_requires_onvif_url():
    with pytest.raises(ValidationError):
        Camera(**_base(ptz_enabled=True))


def test_ptz_enabled_with_onvif_url_ok():
    cam = Camera(**_base(ptz_enabled=True, onvif_url="http://192.168.1.50:8080/onvif/device_service"))
    assert cam.ptz_enabled is True


def test_ptz_speed_defaults_to_50_percent():
    cam = Camera(**_base())
    assert cam.ptz_pan_tilt_speed == 50
    assert cam.ptz_zoom_speed == 50


def test_ptz_speed_accepts_custom_values():
    cam = Camera(**_base(ptz_pan_tilt_speed=20, ptz_zoom_speed=90))
    assert cam.ptz_pan_tilt_speed == 20
    assert cam.ptz_zoom_speed == 90


def test_ptz_speed_rejects_out_of_range():
    with pytest.raises(ValidationError):
        Camera(**_base(ptz_pan_tilt_speed=0))  # below minimum (1)
    with pytest.raises(ValidationError):
        Camera(**_base(ptz_zoom_speed=101))  # above maximum (100)


def test_onvif_url_must_be_http():
    with pytest.raises(ValidationError):
        Camera(**_base(ptz_enabled=True, onvif_url="ftp://x"))


def test_live_scale_format_validated():
    with pytest.raises(ValidationError):
        Camera(**_base(live_scale="not-a-resolution"))
    cam = Camera(**_base(live_scale="854x480"))
    assert cam.live_scale == "854x480"


def test_live_max_bitrate_bounds():
    with pytest.raises(ValidationError):
        Camera(**_base(live_max_bitrate_kbps=10))  # below minimum
    cam = Camera(**_base(live_max_bitrate_kbps=800))
    assert cam.live_max_bitrate_kbps == 800


def test_rtmp_url_must_start_with_rtmp_scheme():
    with pytest.raises(ValidationError):
        Camera(**_base(source_type=SourceType.rtmp, url="rtsp://x/1"))
    cam = Camera(**_base(source_type=SourceType.rtmp, url="rtmp://x/live/stream1"))
    assert cam.url == "rtmp://x/live/stream1"
    cam2 = Camera(**_base(source_type=SourceType.rtmp, url="rtmps://x/live/stream1"))
    assert cam2.url == "rtmps://x/live/stream1"


def test_srt_url_must_start_with_srt_scheme():
    with pytest.raises(ValidationError):
        Camera(**_base(source_type=SourceType.srt, url="rtsp://x/1"))
    cam = Camera(**_base(source_type=SourceType.srt, url="srt://x:9000"))
    assert cam.url == "srt://x:9000"


def test_bare_ip_gets_default_scheme_for_source_type():
    # Adding a camera "by IP" without knowing to type a URL scheme should
    # just work, not be rejected.
    cam = Camera(**_base(source_type=SourceType.rtsp, url="192.168.1.50"))
    assert cam.url == "rtsp://192.168.1.50"

    cam2 = Camera(**_base(source_type=SourceType.rtsp, url="192.168.1.50:554/stream1"))
    assert cam2.url == "rtsp://192.168.1.50:554/stream1"

    cam3 = Camera(**_base(source_type=SourceType.http, url="192.168.1.50/video"))
    assert cam3.url == "http://192.168.1.50/video"


def test_bare_ip_does_not_bypass_scheme_mismatch():
    # A URL that already has *some* scheme is still validated for real -
    # only a fully scheme-less value gets a default prepended.
    with pytest.raises(ValidationError):
        Camera(**_base(source_type=SourceType.rtsp, url="http://192.168.1.50/video"))
