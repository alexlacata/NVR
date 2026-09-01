import pytest


@pytest.mark.asyncio
async def test_requires_auth(client):
    resp = await client.get("/api/cameras")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_then_crud_camera(client):
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    assert resp.status_code == 200
    assert "nvr_session" in resp.cookies

    resp = await client.get("/api/cameras")
    assert resp.status_code == 200
    assert resp.json() == []

    resp = await client.post(
        "/api/cameras",
        json={"name": "Demo test", "source_type": "test", "url": "test:pattern"},
    )
    assert resp.status_code == 201
    camera = resp.json()
    assert camera["id"] == "demo-test"
    assert camera["status"]["state"] in ("starting", "running")

    resp = await client.get("/api/cameras")
    assert len(resp.json()) == 1

    resp = await client.patch(f"/api/cameras/{camera['id']}", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    resp = await client.delete(f"/api/cameras/{camera['id']}")
    assert resp.status_code == 204

    resp = await client.get("/api/cameras")
    assert resp.json() == []


@pytest.mark.asyncio
async def test_bearer_token_also_works(client):
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    token = resp.json()["token"]
    client.cookies.clear()
    resp = await client.get("/api/cameras", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_duplicate_camera_id_rejected(client):
    await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    payload = {"id": "cam1", "name": "Cam 1", "source_type": "test", "url": "test:pattern"}
    resp = await client.post("/api/cameras", json=payload)
    assert resp.status_code == 201
    resp = await client.post("/api/cameras", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_recording_path_traversal_rejected(client):
    await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    await client.post(
        "/api/cameras",
        json={"id": "cam1", "name": "Cam 1", "source_type": "test", "url": "test:pattern"},
    )
    resp = await client.get("/api/cameras/cam1/recordings/..%2F..%2Fsecret.mp4")
    assert resp.status_code in (400, 404)
