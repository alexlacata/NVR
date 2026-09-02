"""WS-Discovery: finds ONVIF cameras on the local network without knowing
their IP address ahead of time, by sending a UDP multicast Probe and
collecting the ProbeMatch replies.

This needs the server to be on the same broadcast domain as the cameras.
In Docker that means `network_mode: host` (see docker-compose.yml) - the
default bridge network does not forward multicast traffic.
"""
from __future__ import annotations

import asyncio
import socket
import uuid
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

WSD_NS = {
    "soap": "http://www.w3.org/2003/05/soap-envelope",
    "wsa": "http://schemas.xmlsoap.org/ws/2004/08/addressing",
    "wsd": "http://schemas.xmlsoap.org/ws/2005/04/discovery",
}

MULTICAST_GROUP = "239.255.255.250"
MULTICAST_PORT = 3702


def _build_probe() -> bytes:
    # Deliberately untyped (no <wsd:Types>) so it matches any WS-Discovery
    # responder, not just ones that advertise the exact NetworkVideoTransmitter
    # type URI - some cheaper cameras are inconsistent about that.
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
        'xmlns:wsd="http://schemas.xmlsoap.org/ws/2005/04/discovery">'
        "<soap:Header>"
        "<wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>"
        f"<wsa:MessageID>uuid:{uuid.uuid4()}</wsa:MessageID>"
        "<wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>"
        "</soap:Header>"
        "<soap:Body><wsd:Probe/></soap:Body>"
        "</soap:Envelope>"
    )
    return xml.encode("utf-8")


@dataclass
class DiscoveredDevice:
    address: str  # the device's WS-Discovery endpoint reference (a UUID URN)
    xaddrs: list[str] = field(default_factory=list)  # candidate ONVIF device service URLs
    scopes: list[str] = field(default_factory=list)


def parse_probe_matches(data: bytes) -> list[DiscoveredDevice]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []
    out = []
    for match in root.findall(".//wsd:ProbeMatches/wsd:ProbeMatch", WSD_NS):
        address = match.findtext(".//wsa:Address", default="", namespaces=WSD_NS) or ""
        xaddrs_text = match.findtext("wsd:XAddrs", default="", namespaces=WSD_NS) or ""
        scopes_text = match.findtext("wsd:Scopes", default="", namespaces=WSD_NS) or ""
        if not address:
            continue
        out.append(DiscoveredDevice(
            address=address,
            xaddrs=xaddrs_text.split(),
            scopes=scopes_text.split(),
        ))
    return out


class _ProbeProtocol(asyncio.DatagramProtocol):
    def __init__(self, results: dict[str, DiscoveredDevice]):
        self.results = results

    def datagram_received(self, data: bytes, addr) -> None:
        for device in parse_probe_matches(data):
            self.results.setdefault(device.address, device)

    def error_received(self, exc: Exception) -> None:  # pragma: no cover - best effort
        pass


async def discover_onvif_devices(timeout_seconds: float = 3.0) -> list[dict]:
    """Broadcasts a WS-Discovery Probe and collects replies for
    `timeout_seconds`. Returns a plain-dict list ready for a JSON response."""
    loop = asyncio.get_running_loop()
    results: dict[str, DiscoveredDevice] = {}

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.bind(("", 0))

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: _ProbeProtocol(results), sock=sock,
    )
    try:
        transport.sendto(_build_probe(), (MULTICAST_GROUP, MULTICAST_PORT))
        await asyncio.sleep(timeout_seconds)
    finally:
        transport.close()

    return [
        {"address": d.address, "xaddrs": d.xaddrs, "scopes": d.scopes}
        for d in results.values()
    ]
