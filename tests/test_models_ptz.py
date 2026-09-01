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
