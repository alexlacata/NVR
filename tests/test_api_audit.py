import pytest


async def _login_admin(client):
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    assert resp.status_code == 200


async def _create_viewer(client, username="bob", password="viewerpass1", permissions=None):
    payload = {"username": username, "password": password, "role": "viewer"}
    if permissions is not None:
        payload["permissions"] = permissions
    resp = await client.post("/api/users", json=payload)
    assert resp.status_code == 201, resp.text


async def _login(client, username, password):
    resp = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200


async def _create_camera_with_recording(client, app_settings, camera_id="cam1"):
    resp = await client.post("/api/cameras", json={
        "id": camera_id, "name": "Cam 1", "source_type": "test", "url": "test://", "record": False,
    })
    assert resp.status_code == 201, resp.text
    rec_dir = app_settings.recordings_dir / camera_id
    rec_dir.mkdir(parents=True, exist_ok=True)
    (rec_dir / "2024-01-01_00-00-00.mp4").write_bytes(b"fake mp4 data")


@pytest.mark.asyncio
async def test_viewing_a_recording_is_audited(client, app_settings):
    await _login_admin(client)
    await _create_camera_with_recording(client, app_settings)

    resp = await client.get("/api/cameras/cam1/recordings/2024-01-01_00-00-00.mp4")
    assert resp.status_code == 200

    audit_resp = await client.get("/api/audit")
    assert audit_resp.status_code == 200
    entries = audit_resp.json()
    assert len(entries) == 1
    assert entries[0]["username"] == "admin"
    assert entries[0]["action"] == "view"
    assert entries[0]["camera_id"] == "cam1"
    assert entries[0]["filename"] == "2024-01-01_00-00-00.mp4"


@pytest.mark.asyncio
async def test_downloading_a_recording_is_audited(client, app_settings):
    await _login_admin(client)
    await _create_camera_with_recording(client, app_settings)

    resp = await client.get("/api/cameras/cam1/recordings/2024-01-01_00-00-00.mp4/download")
    assert resp.status_code == 200

    entries = (await client.get("/api/audit")).json()
    assert len(entries) == 1
    assert entries[0]["action"] == "download"


@pytest.mark.asyncio
async def test_repeated_views_within_cooldown_are_deduped(client, app_settings):
    await _login_admin(client)
    await _create_camera_with_recording(client, app_settings)

    for _ in range(3):
        resp = await client.get("/api/cameras/cam1/recordings/2024-01-01_00-00-00.mp4")
        assert resp.status_code == 200

    entries = (await client.get("/api/audit")).json()
    assert len(entries) == 1  # deduped - simulates HLS <video> range-request scrubbing


@pytest.mark.asyncio
async def test_audit_log_requires_admin(client, app_settings):
    await _login_admin(client)
    await _create_viewer(client)
    await _login(client, "bob", "viewerpass1")

    resp = await client.get("/api/audit")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_audit_log_requires_auth(client):
    resp = await client.get("/api/audit")
    assert resp.status_code == 401
