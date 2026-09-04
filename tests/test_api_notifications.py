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
async def test_get_notification_settings_defaults(client):
    await _login_admin(client)
    resp = await client.get("/api/notifications/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["webhook_enabled"] is False
    assert data["notify_on_motion"] is True


@pytest.mark.asyncio
async def test_patch_notification_settings(client):
    await _login_admin(client)
    resp = await client.patch("/api/notifications/settings", json={
        "webhook_enabled": True,
        "webhook_url": "https://example.com/hook",
        "notify_on_disk_low": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["webhook_enabled"] is True
    assert data["webhook_url"] == "https://example.com/hook"
    assert data["notify_on_disk_low"] is False

    # persisted
    resp2 = await client.get("/api/notifications/settings")
    assert resp2.json()["webhook_url"] == "https://example.com/hook"


@pytest.mark.asyncio
async def test_notifications_require_settings_manage(client):
    await _login_admin(client)
    await _create_viewer(client)  # no settings_manage by default
    await _login(client, "bob", "viewerpass1")

    resp = await client.get("/api/notifications/settings")
    assert resp.status_code == 403
    resp = await client.patch("/api/notifications/settings", json={"webhook_enabled": True})
    assert resp.status_code == 403
    resp = await client.post("/api/notifications/test")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_with_settings_manage_can_access_notifications(client):
    await _login_admin(client)
    await _create_viewer(client, permissions=["settings_manage"])
    await _login(client, "bob", "viewerpass1")

    resp = await client.get("/api/notifications/settings")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_notifications_require_auth(client):
    resp = await client.get("/api/notifications/settings")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_send_test_notification_is_a_noop_with_nothing_configured(client):
    await _login_admin(client)
    resp = await client.post("/api/notifications/test")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
