import pytest

from app.models import SCHEDULE_CELLS


async def _login_admin(client):
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_camera_with_record_schedule(client):
    await _login_admin(client)
    schedule = [False] * SCHEDULE_CELLS
    schedule[9] = True  # Monday 09:00
    resp = await client.post("/api/cameras", json={
        "id": "cam1", "name": "Cam 1", "source_type": "test", "url": "test:pattern",
        "record_schedule": schedule,
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["record_schedule"] == schedule


@pytest.mark.asyncio
async def test_record_schedule_wrong_length_rejected(client):
    await _login_admin(client)
    resp = await client.post("/api/cameras", json={
        "id": "cam1", "name": "Cam 1", "source_type": "test", "url": "test:pattern",
        "record_schedule": [True, False, True],
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_default_record_schedule_is_empty_unrestricted(client):
    await _login_admin(client)
    resp = await client.post("/api/cameras", json={
        "id": "cam1", "name": "Cam 1", "source_type": "test", "url": "test:pattern",
    })
    assert resp.status_code == 201
    assert resp.json()["record_schedule"] == []


@pytest.mark.asyncio
async def test_update_camera_record_schedule_requires_cameras_manage(client):
    await _login_admin(client)
    await client.post("/api/cameras", json={"id": "cam1", "name": "Cam 1", "source_type": "test", "url": "test:pattern"})
    await client.post("/api/users", json={"username": "bob", "password": "viewerpass1", "role": "viewer"})
    await client.post("/api/auth/login", json={"username": "bob", "password": "viewerpass1"})
    resp = await client.patch("/api/cameras/cam1", json={"record_schedule": [True] * SCHEDULE_CELLS})
    assert resp.status_code == 403
