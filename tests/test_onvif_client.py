from unittest.mock import AsyncMock, patch
from xml.etree import ElementTree as ET

import httpx
import pytest

from app.onvif_client import OnvifError, build_envelope, probe_media, WSSE


def test_envelope_without_credentials_has_empty_header():
    xml = build_envelope("", "", "<Foo/>")
    root = ET.fromstring(xml)
    header = root.find("{http://www.w3.org/2003/05/soap-envelope}Header")
    assert header is not None
    assert len(list(header)) == 0


def test_envelope_with_credentials_includes_wsse_digest():
    xml = build_envelope("admin", "s3cret", "<Foo/>")
    assert f'xmlns="{WSSE}"' in xml
    assert "<Username>admin</Username>" in xml
    assert "PasswordDigest" in xml
    root = ET.fromstring(xml)
    body = root.find("{http://www.w3.org/2003/05/soap-envelope}Body")
    assert body is not None
    assert body[0].tag == "Foo"


def test_envelope_escapes_special_chars_in_username():
    xml = build_envelope("a<dmin>&", "pw", "<Foo/>")
    # must remain well-formed XML
    ET.fromstring(xml)
    assert "&lt;dmin&gt;&amp;" in xml


_GET_SERVICES_RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
<soap:Body>
<GetServicesResponse xmlns="http://www.onvif.org/ver10/device/wsdl">
<Service>
<Namespace>http://www.onvif.org/ver10/device/wsdl</Namespace>
<XAddr>http://192.168.1.50/onvif/device_service</XAddr>
</Service>
<Service>
<Namespace>http://www.onvif.org/ver10/media/wsdl</Namespace>
<XAddr>http://192.168.1.50/onvif/media_service</XAddr>
</Service>
</GetServicesResponse>
</soap:Body>
</soap:Envelope>"""

_GET_PROFILES_RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
<soap:Body>
<GetProfilesResponse xmlns="http://www.onvif.org/ver10/media/wsdl">
<Profiles token="profile1">
<Name>MainStream</Name>
<VideoEncoderConfiguration xmlns="http://www.onvif.org/ver10/schema">
<Resolution><Width>1920</Width><Height>1080</Height></Resolution>
</VideoEncoderConfiguration>
</Profiles>
</GetProfilesResponse>
</soap:Body>
</soap:Envelope>"""

_GET_STREAM_URI_RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
<soap:Body>
<GetStreamUriResponse xmlns="http://www.onvif.org/ver10/media/wsdl">
<MediaUri>
<Uri>rtsp://192.168.1.50:554/Streaming/Channels/101</Uri>
</MediaUri>
</GetStreamUriResponse>
</soap:Body>
</soap:Envelope>"""

_SOAP_FAULT_RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
<soap:Body>
<soap:Fault><soap:Reason><soap:Text>Sender not authorized</soap:Text></soap:Reason></soap:Fault>
</soap:Body>
</soap:Envelope>"""


def _resp(body: bytes) -> httpx.Response:
    return httpx.Response(200, content=body, request=httpx.Request("POST", "http://x"))


@pytest.mark.asyncio
async def test_probe_media_returns_profile_with_embedded_credentials():
    responses = [_resp(_GET_SERVICES_RESPONSE), _resp(_GET_PROFILES_RESPONSE), _resp(_GET_STREAM_URI_RESPONSE)]
    with patch.object(httpx.AsyncClient, "post", AsyncMock(side_effect=responses)):
        profiles = await probe_media("http://192.168.1.50/onvif/device_service", "admin", "s3cret")

    assert len(profiles) == 1
    p = profiles[0]
    assert p.token == "profile1"
    assert p.name == "MainStream"
    assert p.resolution == "1920x1080"
    assert p.stream_uri == "rtsp://admin:s3cret@192.168.1.50:554/Streaming/Channels/101"


@pytest.mark.asyncio
async def test_probe_media_no_media_service_raises():
    services_without_media = _resp(_GET_SERVICES_RESPONSE.replace(b"ver10/media/wsdl", b"ver10/imaging/wsdl"))
    with patch.object(httpx.AsyncClient, "post", AsyncMock(return_value=services_without_media)):
        with pytest.raises(OnvifError):
            await probe_media("http://192.168.1.50/onvif/device_service", "admin", "s3cret")


@pytest.mark.asyncio
async def test_probe_media_soap_fault_raises_onvif_error():
    with patch.object(httpx.AsyncClient, "post", AsyncMock(return_value=_resp(_SOAP_FAULT_RESPONSE))):
        with pytest.raises(OnvifError):
            await probe_media("http://192.168.1.50/onvif/device_service", "admin", "wrong")


@pytest.mark.asyncio
async def test_probe_media_profile_survives_stream_uri_failure():
    # GetStreamUri failing for one profile shouldn't drop the profile entirely
    responses = [_resp(_GET_SERVICES_RESPONSE), _resp(_GET_PROFILES_RESPONSE), _resp(_SOAP_FAULT_RESPONSE)]
    with patch.object(httpx.AsyncClient, "post", AsyncMock(side_effect=responses)):
        profiles = await probe_media("http://192.168.1.50/onvif/device_service", "admin", "s3cret")
    assert len(profiles) == 1
    assert profiles[0].stream_uri is None
