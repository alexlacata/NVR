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
async def test_get_router_credentials_defaults(client):
    await _login_admin(client)
    resp = await client.get("/api/router-credentials")
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] is None
    assert data["password"] is None


@pytest.mark.asyncio
async def test_patch_router_credentials(client):
    await _login_admin(client)
    resp = await client.patch("/api/router-credentials", json={"username": "admin", "password": "hunter2"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "admin"
    assert data["password"] == "hunter2"

    resp2 = await client.get("/api/router-credentials")
    assert resp2.json()["username"] == "admin"
    assert resp2.json()["password"] == "hunter2"


@pytest.mark.asyncio
async def test_router_credentials_require_settings_manage(client):
    await _login_admin(client)
    await _create_viewer(client)  # no settings_manage by default
    await _login(client, "bob", "viewerpass1")

    resp = await client.get("/api/router-credentials")
    assert resp.status_code == 403
    resp = await client.patch("/api/router-credentials", json={"username": "admin"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_with_settings_manage_can_access_router_credentials(client):
    await _login_admin(client)
    await _create_viewer(client, permissions=["settings_manage"])
    await _login(client, "bob", "viewerpass1")

    resp = await client.get("/api/router-credentials")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_router_credentials_require_auth(client):
    resp = await client.get("/api/router-credentials")
    assert resp.status_code == 401
