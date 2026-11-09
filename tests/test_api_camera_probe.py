from unittest.mock import AsyncMock, patch

import pytest

from app.camera_probe import ProbeResult


@pytest.mark.asyncio
async def test_test_connection_requires_auth(client):
    resp = await client.post("/api/cameras/test-connection", json={"source_type": "rtsp", "url": "rtsp://x/1"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_test_connection_success(client):
    await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    with patch(
        "app.api.routes_cameras.probe_camera_source",
        AsyncMock(return_value=ProbeResult(ok=True, resolution="1920x1080")),
    ):
        resp = await client.post("/api/cameras/test-connection", json={"source_type": "rtsp", "url": "rtsp://x/1"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "resolution": "1920x1080", "detail": None}


@pytest.mark.asyncio
async def test_test_connection_failure(client):
    await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    with patch(
        "app.api.routes_cameras.probe_camera_source",
        AsyncMock(return_value=ProbeResult(ok=False, detail="Connection timed out")),
    ):
        resp = await client.post("/api/cameras/test-connection", json={"source_type": "rtsp", "url": "rtsp://x/1"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": False, "resolution": None, "detail": "Connection timed out"}


@pytest.mark.asyncio
async def test_test_connection_requires_cameras_manage_permission(client):
    await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    await client.post("/api/users", json={
        "username": "viewer1", "password": "ViewerPass1!", "role": "viewer", "permissions": [],
    })
    await client.post("/api/auth/logout")
    await client.post("/api/auth/login", json={"username": "viewer1", "password": "ViewerPass1!"})
    resp = await client.post("/api/cameras/test-connection", json={"source_type": "rtsp", "url": "rtsp://x/1"})
    assert resp.status_code == 403
