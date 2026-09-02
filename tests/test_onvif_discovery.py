from app.onvif_discovery import parse_probe_matches, _build_probe


def test_build_probe_is_well_formed_and_untyped():
    xml = _build_probe()
    assert b"<wsd:Probe/>" in xml
    assert b"MessageID" in xml


def test_parse_probe_matches_extracts_address_xaddrs_scopes():
    data = b"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
               xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
               xmlns:wsd="http://schemas.xmlsoap.org/ws/2005/04/discovery">
<soap:Body>
<wsd:ProbeMatches>
<wsd:ProbeMatch>
<wsa:EndpointReference><wsa:Address>urn:uuid:12345678-abcd-1234-abcd-1234567890ab</wsa:Address></wsa:EndpointReference>
<wsd:Types>dn:NetworkVideoTransmitter</wsd:Types>
<wsd:Scopes>onvif://www.onvif.org/name/HIKVISION onvif://www.onvif.org/hardware/DS-2CD</wsd:Scopes>
<wsd:XAddrs>http://192.168.1.51/onvif/device_service</wsd:XAddrs>
</wsd:ProbeMatch>
</wsd:ProbeMatches>
</soap:Body>
</soap:Envelope>"""
    devices = parse_probe_matches(data)
    assert len(devices) == 1
    d = devices[0]
    assert d.address == "urn:uuid:12345678-abcd-1234-abcd-1234567890ab"
    assert d.xaddrs == ["http://192.168.1.51/onvif/device_service"]
    assert "onvif://www.onvif.org/name/HIKVISION" in d.scopes


def test_parse_probe_matches_multiple_devices():
    data = b"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
               xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
               xmlns:wsd="http://schemas.xmlsoap.org/ws/2005/04/discovery">
<soap:Body><wsd:ProbeMatches>
<wsd:ProbeMatch>
<wsa:EndpointReference><wsa:Address>urn:uuid:aaaa</wsa:Address></wsa:EndpointReference>
<wsd:XAddrs>http://192.168.1.51/onvif/device_service</wsd:XAddrs>
</wsd:ProbeMatch>
<wsd:ProbeMatch>
<wsa:EndpointReference><wsa:Address>urn:uuid:bbbb</wsa:Address></wsa:EndpointReference>
<wsd:XAddrs>http://192.168.1.52/onvif/device_service</wsd:XAddrs>
</wsd:ProbeMatch>
</wsd:ProbeMatches></soap:Body>
</soap:Envelope>"""
    devices = parse_probe_matches(data)
    assert {d.address for d in devices} == {"urn:uuid:aaaa", "urn:uuid:bbbb"}


def test_parse_probe_matches_malformed_xml_returns_empty():
    assert parse_probe_matches(b"not xml at all") == []


def test_parse_probe_matches_no_matches_returns_empty():
    data = b'<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"><soap:Body/></soap:Envelope>'
    assert parse_probe_matches(data) == []
