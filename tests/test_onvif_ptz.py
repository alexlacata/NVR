from xml.etree import ElementTree as ET

from app.onvif_ptz import build_envelope, WSSE


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
