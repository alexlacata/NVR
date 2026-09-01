import pytest


@pytest.mark.asyncio
async def test_ptz_move_rejected_for_non_ptz_camera(client):
    await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    await client.post(
        "/api/cameras",
        json={"id": "cam1", "name": "Cam 1", "source_type": "test", "url": "test:pattern"},
    )
    resp = await client.post("/api/cameras/cam1/ptz/move", json={"pan": 0.5, "tilt": 0, "zoom": 0})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_ptz_move_on_unreachable_camera_returns_502(client):
    await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    await client.post(
        "/api/cameras",
        json={
            "id": "cam1",
            "name": "Cam 1",
            "source_type": "test",
            "url": "test:pattern",
            "ptz_enabled": True,
            "onvif_url": "http://127.0.0.1:1/onvif/device_service",
        },
    )
    resp = await client.post("/api/cameras/cam1/ptz/move", json={"pan": 0.5, "tilt": 0, "zoom": 0})
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_ptz_requires_auth(client):
    resp = await client.post("/api/cameras/cam1/ptz/move", json={"pan": 0, "tilt": 0, "zoom": 0})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_camera_ptz_enabled_requires_onvif_url(client):
    await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    resp = await client.post(
        "/api/cameras",
        json={"id": "cam1", "name": "Cam 1", "source_type": "test", "url": "test:pattern", "ptz_enabled": True},
    )
    assert resp.status_code == 422
