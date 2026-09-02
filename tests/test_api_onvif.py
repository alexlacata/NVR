from unittest.mock import AsyncMock, patch

import pytest

from app.onvif_client import MediaProfile, OnvifError


@pytest.mark.asyncio
async def test_onvif_probe_requires_auth(client):
    resp = await client.post("/api/onvif/probe", json={"onvif_url": "http://192.168.1.50/onvif/device_service"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_onvif_probe_rejects_bad_url(client):
    await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    resp = await client.post("/api/onvif/probe", json={"onvif_url": "not-a-url"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_onvif_probe_returns_profiles(client):
    await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    fake_profiles = [
        MediaProfile(token="p1", name="Main", resolution="1920x1080", stream_uri="rtsp://a:b@192.168.1.50:554/ch1"),
    ]
    with patch("app.api.routes_onvif.probe_media", AsyncMock(return_value=fake_profiles)):
        resp = await client.post("/api/onvif/probe", json={
            "onvif_url": "http://192.168.1.50/onvif/device_service",
            "username": "a", "password": "b",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data == [{"token": "p1", "name": "Main", "resolution": "1920x1080", "stream_uri": "rtsp://a:b@192.168.1.50:554/ch1"}]


@pytest.mark.asyncio
async def test_onvif_probe_no_profiles_404(client):
    await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    with patch("app.api.routes_onvif.probe_media", AsyncMock(return_value=[])):
        resp = await client.post("/api/onvif/probe", json={"onvif_url": "http://192.168.1.50/onvif/device_service"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_onvif_probe_onvif_error_returns_502(client):
    await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    with patch("app.api.routes_onvif.probe_media", AsyncMock(side_effect=OnvifError("camera injoignable"))):
        resp = await client.post("/api/onvif/probe", json={"onvif_url": "http://192.168.1.50/onvif/device_service"})
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_onvif_discover_requires_auth(client):
    resp = await client.post("/api/onvif/discover")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_onvif_discover_returns_list(client):
    await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    with patch("app.api.routes_onvif.discover_onvif_devices", AsyncMock(return_value=[])):
        resp = await client.post("/api/onvif/discover")
    assert resp.status_code == 200
    assert resp.json() == []
