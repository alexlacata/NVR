import pytest


async def _login_admin(client):
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_motion_status_requires_auth(client):
    resp = await client.get("/api/cameras/cam1/motion")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_motion_status_missing_camera_404(client):
    await _login_admin(client)
    resp = await client.get("/api/cameras/nope/motion")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_motion_status_default_state_for_new_camera(client):
    await _login_admin(client)
    await client.post("/api/cameras", json={"id": "cam1", "name": "Cam 1", "source_type": "test", "url": "test:pattern"})
    resp = await client.get("/api/cameras/cam1/motion")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active"] is False
    assert data["last_motion_at"] is None
    assert data["recent_events"] == []
    assert data["grid_cols"] * data["grid_rows"] > 0


@pytest.mark.asyncio
async def test_motion_status_visible_to_viewer(client):
    # motion status is read-only telemetry, not gated behind cameras_manage
    await _login_admin(client)
    await client.post("/api/cameras", json={"id": "cam1", "name": "Cam 1", "source_type": "test", "url": "test:pattern"})
    await client.post("/api/users", json={"username": "bob", "password": "viewerpass1", "role": "viewer"})
    await client.post("/api/auth/login", json={"username": "bob", "password": "viewerpass1"})
    resp = await client.get("/api/cameras/cam1/motion")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_camera_with_motion_fields(client):
    await _login_admin(client)
    resp = await client.post("/api/cameras", json={
        "id": "cam1", "name": "Cam 1", "source_type": "test", "url": "test:pattern",
        "motion_enabled": True, "motion_sensitivity": 80,
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["motion_enabled"] is True
    assert data["motion_sensitivity"] == 80


@pytest.mark.asyncio
async def test_motion_mask_grid_wrong_length_rejected(client):
    await _login_admin(client)
    resp = await client.post("/api/cameras", json={
        "id": "cam1", "name": "Cam 1", "source_type": "test", "url": "test:pattern",
        "motion_mask_grid": [True, False],  # not 48 entries
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_motion_mask_grid_full_length_accepted(client):
    await _login_admin(client)
    grid = [False] * 47 + [True]
    resp = await client.post("/api/cameras", json={
        "id": "cam1", "name": "Cam 1", "source_type": "test", "url": "test:pattern",
        "motion_mask_grid": grid,
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["motion_mask_grid"] == grid


@pytest.mark.asyncio
async def test_update_camera_motion_settings_requires_cameras_manage(client):
    await _login_admin(client)
    await client.post("/api/cameras", json={"id": "cam1", "name": "Cam 1", "source_type": "test", "url": "test:pattern"})
    await client.post("/api/users", json={"username": "bob", "password": "viewerpass1", "role": "viewer"})
    await client.post("/api/auth/login", json={"username": "bob", "password": "viewerpass1"})
    resp = await client.patch("/api/cameras/cam1", json={"motion_enabled": True})
    assert resp.status_code == 403
