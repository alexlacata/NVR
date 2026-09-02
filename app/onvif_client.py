"""Minimal ONVIF client: PTZ (pan/tilt/zoom) control and media/stream
discovery.

Implemented by hand against the ONVIF SOAP/WS-Security spec instead of
pulling in a full ONVIF/zeep dependency: this only needs a handful of
simple, stable SOAP calls (GetServices, GetProfiles, GetStreamUri,
ContinuousMove, Stop, GetPresets, SetPreset, GotoPreset, RemovePreset), and
hand-rolling them keeps the dependency footprint small.

ONVIF is what makes this generic across camera brands: Hikvision, Uniview,
Dahua, Axis, Reolink and effectively every modern IP camera implement the
same ONVIF Profile S/T services, so a single client here covers all of
them rather than needing a vendor-specific integration each.

Reference: ONVIF Core Specification (WS-Security UsernameToken digest) and
the ONVIF Media (ver10/media/wsdl) and PTZ (ver20/ptz/wsdl) service WSDLs.
"""
from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

import httpx

SOAP_ENV = "http://www.w3.org/2003/05/soap-envelope"
WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
NS = {
    "soap": SOAP_ENV,
    "device": "http://www.onvif.org/ver10/device/wsdl",
    "media": "http://www.onvif.org/ver10/media/wsdl",
    "ptz": "http://www.onvif.org/ver20/ptz/wsdl",
    "tt": "http://www.onvif.org/ver10/schema",
}


class OnvifError(RuntimeError):
    pass


def _wsse_header(username: str, password: str) -> str:
    nonce = os.urandom(16)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest = base64.b64encode(
        hashlib.sha1(nonce + created.encode("utf-8") + password.encode("utf-8")).digest()
    ).decode()
    nonce_b64 = base64.b64encode(nonce).decode()
    return (
        f'<Security xmlns="{WSSE}" xmlns:wsu="{WSU}">'
        "<UsernameToken>"
        f"<Username>{_xml_escape(username)}</Username>"
        f'<Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</Password>'
        f'<Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce_b64}</Nonce>'
        f"<wsu:Created>{created}</wsu:Created>"
        "</UsernameToken>"
        "</Security>"
    )


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;").replace("'", "&apos;")
    )


def build_envelope(username: str, password: str, body_xml: str) -> str:
    header = _wsse_header(username, password) if username else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<soap:Envelope xmlns:soap="{SOAP_ENV}">'
        f"<soap:Header>{header}</soap:Header>"
        f"<soap:Body>{body_xml}</soap:Body>"
        "</soap:Envelope>"
    )


async def _soap_call(client: httpx.AsyncClient, url: str, username: str, password: str, body_xml: str) -> ET.Element:
    envelope = build_envelope(username, password, body_xml)
    try:
        resp = await client.post(
            url,
            content=envelope.encode("utf-8"),
            headers={"Content-Type": "application/soap+xml; charset=utf-8"},
            timeout=10,
        )
    except httpx.HTTPError as exc:
        raise OnvifError(f"Camera ONVIF injoignable ({url}): {exc}") from exc
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as exc:
        raise OnvifError(f"Reponse ONVIF invalide (HTTP {resp.status_code})") from exc
    fault = root.find(".//soap:Body/soap:Fault", NS)
    if fault is not None:
        text = "".join(fault.itertext()).strip()
        raise OnvifError(f"Erreur ONVIF: {text or 'inconnue'}")
    if resp.status_code >= 400:
        raise OnvifError(f"Erreur ONVIF HTTP {resp.status_code}")
    return root


@dataclass
class Preset:
    token: str
    name: str


class OnvifPTZClient:
    """PTZ client for one camera. Discovers the Media/PTZ service addresses
    and a profile token lazily, on first use, and caches them."""

    def __init__(self, device_url: str, username: str, password: str):
        self.device_url = device_url
        self.username = username or ""
        self.password = password or ""
        self._media_url: Optional[str] = None
        self._ptz_url: Optional[str] = None
        self._profile_token: Optional[str] = None

    def matches(self, device_url: str, username: str, password: str) -> bool:
        return self.device_url == device_url and self.username == (username or "") and self.password == (password or "")

    async def _ensure_discovered(self, client: httpx.AsyncClient) -> None:
        if self._ptz_url and self._profile_token:
            return
        root = await _soap_call(
            client, self.device_url, self.username, self.password,
            '<GetServices xmlns="http://www.onvif.org/ver10/device/wsdl"><IncludeCapability>false</IncludeCapability></GetServices>',
        )
        for service in root.findall(".//device:Service", NS):
            namespace = (service.findtext("device:Namespace", default="", namespaces=NS) or "")
            xaddr = service.findtext("device:XAddr", default="", namespaces=NS)
            if namespace.endswith("/ver10/media/wsdl"):
                self._media_url = xaddr
            elif namespace.endswith("/ver20/ptz/wsdl"):
                self._ptz_url = xaddr
        if not self._media_url or not self._ptz_url:
            raise OnvifError("Cette camera ne semble pas exposer de service PTZ ONVIF")

        root = await _soap_call(
            client, self._media_url, self.username, self.password,
            '<GetProfiles xmlns="http://www.onvif.org/ver10/media/wsdl"/>',
        )
        profile = root.find(".//media:Profiles", NS)
        if profile is None:
            raise OnvifError("Aucun profil media ONVIF trouve")
        self._profile_token = profile.get("token")

    async def continuous_move(self, pan: float, tilt: float, zoom: float = 0.0) -> None:
        pan = max(-1.0, min(1.0, pan))
        tilt = max(-1.0, min(1.0, tilt))
        zoom = max(-1.0, min(1.0, zoom))
        async with httpx.AsyncClient() as client:
            await self._ensure_discovered(client)
            body = (
                '<ContinuousMove xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
                f"<ProfileToken>{self._profile_token}</ProfileToken>"
                '<Velocity xmlns:tt="http://www.onvif.org/ver10/schema">'
                f'<tt:PanTilt x="{pan}" y="{tilt}"/>'
                f'<tt:Zoom x="{zoom}"/>'
                "</Velocity>"
                "</ContinuousMove>"
            )
            await _soap_call(client, self._ptz_url, self.username, self.password, body)

    async def stop(self) -> None:
        async with httpx.AsyncClient() as client:
            await self._ensure_discovered(client)
            body = (
                '<Stop xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
                f"<ProfileToken>{self._profile_token}</ProfileToken>"
                "<PanTilt>true</PanTilt><Zoom>true</Zoom>"
                "</Stop>"
            )
            await _soap_call(client, self._ptz_url, self.username, self.password, body)

    async def get_presets(self) -> list[Preset]:
        async with httpx.AsyncClient() as client:
            await self._ensure_discovered(client)
            body = (
                '<GetPresets xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
                f"<ProfileToken>{self._profile_token}</ProfileToken>"
                "</GetPresets>"
            )
            root = await _soap_call(client, self._ptz_url, self.username, self.password, body)
            presets = []
            for p in root.findall(".//ptz:Preset", NS):
                token = p.get("token", "")
                name = p.findtext("ptz:Name", default="", namespaces=NS) or token
                presets.append(Preset(token=token, name=name))
            return presets

    async def set_preset(self, name: str) -> str:
        async with httpx.AsyncClient() as client:
            await self._ensure_discovered(client)
            body = (
                '<SetPreset xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
                f"<ProfileToken>{self._profile_token}</ProfileToken>"
                f"<PresetName>{_xml_escape(name)}</PresetName>"
                "</SetPreset>"
            )
            root = await _soap_call(client, self._ptz_url, self.username, self.password, body)
            token = root.findtext(".//ptz:PresetToken", default="", namespaces=NS)
            return token or ""

    async def goto_preset(self, preset_token: str) -> None:
        async with httpx.AsyncClient() as client:
            await self._ensure_discovered(client)
            body = (
                '<GotoPreset xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
                f"<ProfileToken>{self._profile_token}</ProfileToken>"
                f"<PresetToken>{preset_token}</PresetToken>"
                "</GotoPreset>"
            )
            await _soap_call(client, self._ptz_url, self.username, self.password, body)

    async def remove_preset(self, preset_token: str) -> None:
        async with httpx.AsyncClient() as client:
            await self._ensure_discovered(client)
            body = (
                '<RemovePreset xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
                f"<ProfileToken>{self._profile_token}</ProfileToken>"
                f"<PresetToken>{preset_token}</PresetToken>"
                "</RemovePreset>"
            )
            await _soap_call(client, self._ptz_url, self.username, self.password, body)


@dataclass
class MediaProfile:
    token: str
    name: str
    resolution: Optional[str]  # "1920x1080", or None if not reported
    stream_uri: Optional[str]  # rtsp:// URL for this profile, credentials embedded


def _embed_credentials(uri: str, username: str, password: str) -> str:
    """ONVIF's GetStreamUri normally returns a bare rtsp:// URL - the
    camera expects the same ONVIF username/password at the RTSP level.
    Embed them so the URL is directly usable as a Camera.url."""
    if not username or not uri:
        return uri
    parts = urlsplit(uri)
    if "@" in parts.netloc:
        return uri  # already carries credentials
    netloc = f"{quote(username, safe='')}:{quote(password, safe='')}@{parts.netloc}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


async def probe_media(device_url: str, username: str, password: str) -> list[MediaProfile]:
    """Discover the media profiles (and their RTSP stream URLs) an
    ONVIF-compliant camera exposes. Works for any brand - Hikvision,
    Uniview, Dahua, Axis, Reolink, ... - without vendor-specific code,
    and needs no PTZ support on the camera."""
    username = username or ""
    password = password or ""
    async with httpx.AsyncClient() as client:
        root = await _soap_call(
            client, device_url, username, password,
            '<GetServices xmlns="http://www.onvif.org/ver10/device/wsdl"><IncludeCapability>false</IncludeCapability></GetServices>',
        )
        media_url = None
        for service in root.findall(".//device:Service", NS):
            namespace = service.findtext("device:Namespace", default="", namespaces=NS) or ""
            if namespace.endswith("/ver10/media/wsdl"):
                media_url = service.findtext("device:XAddr", default="", namespaces=NS)
        if not media_url:
            raise OnvifError("Cette camera ne semble pas exposer de service media ONVIF")

        root = await _soap_call(
            client, media_url, username, password,
            '<GetProfiles xmlns="http://www.onvif.org/ver10/media/wsdl"/>',
        )
        profiles: list[MediaProfile] = []
        for p in root.findall(".//media:Profiles", NS):
            token = p.get("token", "")
            name = p.findtext("media:Name", default=token, namespaces=NS) or token

            resolution = None
            vres = p.find(".//tt:VideoEncoderConfiguration/tt:Resolution", NS)
            if vres is not None:
                w = vres.findtext("tt:Width", default="", namespaces=NS)
                h = vres.findtext("tt:Height", default="", namespaces=NS)
                if w and h:
                    resolution = f"{w}x{h}"

            stream_uri = None
            stream_body = (
                '<GetStreamUri xmlns="http://www.onvif.org/ver10/media/wsdl">'
                '<StreamSetup>'
                '<Stream xmlns="http://www.onvif.org/ver10/schema">RTP-Unicast</Stream>'
                '<Transport xmlns="http://www.onvif.org/ver10/schema"><Protocol>RTSP</Protocol></Transport>'
                '</StreamSetup>'
                f'<ProfileToken>{token}</ProfileToken>'
                '</GetStreamUri>'
            )
            try:
                stream_root = await _soap_call(client, media_url, username, password, stream_body)
                uri = stream_root.findtext(".//media:MediaUri/media:Uri", default="", namespaces=NS)
                if uri:
                    stream_uri = _embed_credentials(uri, username, password)
            except OnvifError:
                pass  # this profile just won't have a stream_uri; others might

            profiles.append(MediaProfile(token=token, name=name, resolution=resolution, stream_uri=stream_uri))

        return profiles
