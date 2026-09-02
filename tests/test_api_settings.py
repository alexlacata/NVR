import pytest


async def _login_admin(client):
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_settings_requires_auth(client):
    resp = await client.get("/api/settings")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_viewer_cannot_read_or_write_settings(client):
    await _login_admin(client)
    await client.post("/api/users", json={"username": "bob", "password": "viewerpass1", "role": "viewer"})
    await client.post("/api/auth/login", json={"username": "bob", "password": "viewerpass1"})

    resp = await client.get("/api/settings")
    assert resp.status_code == 403
    resp = await client.patch("/api/settings", json={"retention_days": 5})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_settings_returns_defaults(client, app_settings):
    await _login_admin(client)
    resp = await client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["retention_days"] == app_settings.retention_days
    assert data["segment_seconds"] == app_settings.segment_seconds


@pytest.mark.asyncio
async def test_patch_settings_updates_and_persists(client, app_settings):
    await _login_admin(client)
    resp = await client.patch("/api/settings", json={"retention_days": 30, "min_free_disk_percent": 15})
    assert resp.status_code == 200
    data = resp.json()
    assert data["retention_days"] == 30
    assert data["min_free_disk_percent"] == 15

    # the live Settings object used by the rest of the app is updated too
    assert app_settings.retention_days == 30
    assert app_settings.min_free_disk_percent == 15

    # persisted to disk: a fresh SettingsStore sees the same override
    from app.settings_store import SettingsStore
    store2 = SettingsStore(app_settings.runtime_settings_file)
    overrides = store2.load_overrides()
    assert overrides["retention_days"] == 30


@pytest.mark.asyncio
async def test_patch_settings_partial_update_leaves_others_untouched(client, app_settings):
    await _login_admin(client)
    await client.patch("/api/settings", json={"retention_days": 30})
    resp = await client.patch("/api/settings", json={"min_free_disk_percent": 20})
    assert resp.status_code == 200
    data = resp.json()
    assert data["retention_days"] == 30  # unaffected by the second patch
    assert data["min_free_disk_percent"] == 20


@pytest.mark.asyncio
async def test_patch_settings_rejects_out_of_range(client):
    await _login_admin(client)
    resp = await client.patch("/api/settings", json={"retention_days": 0})
    assert resp.status_code == 422
    resp = await client.patch("/api/settings", json={"min_free_disk_percent": 200})
    assert resp.status_code == 422
