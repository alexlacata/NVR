import hashlib

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


async def _create_camera_with_recording(client, app_settings, camera_id="cam1", content=b"fake mp4 data"):
    resp = await client.post("/api/cameras", json={
        "id": camera_id, "name": "Cam 1", "source_type": "test", "url": "test://", "record": False,
    })
    assert resp.status_code == 201, resp.text
    rec_dir = app_settings.recordings_dir / camera_id
    rec_dir.mkdir(parents=True, exist_ok=True)
    (rec_dir / "2024-01-01_00-00-00.mp4").write_bytes(content)


@pytest.mark.asyncio
async def test_checksum_matches_real_sha256(client, app_settings):
    await _login_admin(client)
    content = b"some recording bytes" * 1000
    await _create_camera_with_recording(client, app_settings, content=content)

    resp = await client.get("/api/cameras/cam1/recordings/2024-01-01_00-00-00.mp4/checksum")
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "2024-01-01_00-00-00.mp4"
    assert data["size_bytes"] == len(content)
    assert data["sha256"] == hashlib.sha256(content).hexdigest()


@pytest.mark.asyncio
async def test_checksum_missing_recording_404(client, app_settings):
    await _login_admin(client)
    resp = await client.post("/api/cameras", json={
        "id": "cam1", "name": "Cam 1", "source_type": "test", "url": "test://", "record": False,
    })
    assert resp.status_code == 201
    resp = await client.get("/api/cameras/cam1/recordings/2024-01-01_00-00-00.mp4/checksum")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_checksum_requires_recordings_download_permission(client, app_settings):
    await _login_admin(client)
    await _create_camera_with_recording(client, app_settings)
    await _create_viewer(client, permissions=["ptz_control"])  # recordings_download withheld
    await _login(client, "bob", "viewerpass1")

    resp = await client.get("/api/cameras/cam1/recordings/2024-01-01_00-00-00.mp4/checksum")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_checksum_rejects_path_traversal(client, app_settings):
    await _login_admin(client)
    await _create_camera_with_recording(client, app_settings)
    resp = await client.get("/api/cameras/cam1/recordings/..%2f..%2fapp%2fmain.py/checksum")
    assert resp.status_code in (400, 404)
