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


@pytest.mark.asyncio
async def test_backup_status_when_disabled(client, app_settings):
    await _login_admin(client)
    resp = await client.get("/api/backup/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert data["backup_dir"] is None
    assert data["last_run_at"] is None


@pytest.mark.asyncio
async def test_run_backup_now_copies_and_updates_status(client, app_settings, tmp_path):
    await _login_admin(client)
    app_settings.backup_dir = str(tmp_path / "backup-dest")

    rec_dir = app_settings.recordings_dir / "cam1"
    rec_dir.mkdir(parents=True, exist_ok=True)
    (rec_dir / "2024-01-01_00-00-00.mp4").write_bytes(b"hello" * 100)

    resp = await client.post("/api/backup/run")
    assert resp.status_code == 200
    data = resp.json()
    assert data["copied_files"] == 1

    status_resp = await client.get("/api/backup/status")
    status_data = status_resp.json()
    assert status_data["enabled"] is True
    assert status_data["last_copied_files"] == 1
    assert status_data["last_run_at"] is not None


@pytest.mark.asyncio
async def test_backup_requires_settings_manage(client):
    await _login_admin(client)
    await _create_viewer(client)
    await _login(client, "bob", "viewerpass1")

    resp = await client.get("/api/backup/status")
    assert resp.status_code == 403
    resp = await client.post("/api/backup/run")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_backup_requires_auth(client):
    resp = await client.get("/api/backup/status")
    assert resp.status_code == 401
