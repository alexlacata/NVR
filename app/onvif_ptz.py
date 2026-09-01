"""Minimal ONVIF client for PTZ (pan/tilt/zoom) control.

Implemented by hand against the ONVIF SOAP/WS-Security spec instead of
pulling in a full ONVIF/zeep dependency: PTZ control is a handful of simple,
stable SOAP calls (GetServices, GetProfiles, ContinuousMove, Stop,
GetPresets, SetPreset, GotoPreset, RemovePreset), and this keeps the
dependency footprint small.

Reference: ONVIF Core Specification (WS-Security UsernameToken digest) and
the ONVIF PTZ service WSDL (ver20/ptz/wsdl).
"""
from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
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
