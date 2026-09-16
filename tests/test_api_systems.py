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
    return resp.json()


async def _login(client, username, password):
    resp = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_systems_empty_by_default(client):
    await _login_admin(client)
    resp = await client.get("/api/systems")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_system_normalizes_url_and_assigns_id(client):
    await _login_admin(client)
    resp = await client.post("/api/systems", json={"name": "Maison", "url": "192.168.1.50:8000"})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["id"] == "maison"
    assert data["url"] == "http://192.168.1.50:8000"  # scheme auto-prepended
    assert data["name"] == "Maison"


@pytest.mark.asyncio
async def test_create_system_keeps_explicit_https(client):
    await _login_admin(client)
    resp = await client.post("/api/systems", json={"name": "Chalet", "url": "https://chalet.example.com/"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["url"] == "https://chalet.example.com"  # trailing slash trimmed


@pytest.mark.asyncio
async def test_create_system_rejects_empty_url(client):
    await _login_admin(client)
    resp = await client.post("/api/systems", json={"name": "Vide", "url": "   "})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_slug_gets_suffixed(client):
    await _login_admin(client)
    r1 = await client.post("/api/systems", json={"name": "Maison", "url": "10.0.0.1"})
    r2 = await client.post("/api/systems", json={"name": "Maison", "url": "10.0.0.2"})
    assert r1.json()["id"] == "maison"
    assert r2.json()["id"] == "maison-2"


@pytest.mark.asyncio
async def test_update_system(client):
    await _login_admin(client)
    created = (await client.post("/api/systems", json={"name": "Maison", "url": "10.0.0.1"})).json()
    resp = await client.patch(f"/api/systems/{created['id']}", json={"notes": "Derriere le routeur 4G"})
    assert resp.status_code == 200
    assert resp.json()["notes"] == "Derriere le routeur 4G"
    assert resp.json()["name"] == "Maison"  # untouched fields survive a partial update


@pytest.mark.asyncio
async def test_system_ssh_defaults_to_root_22_when_not_specified(client):
    # Nothing to fill in for SSH to get a working door: leaving both fields
    # out at creation still gets the near-universal root/22 default, not None.
    await _login_admin(client)
    created = (await client.post("/api/systems", json={"name": "Maison", "url": "10.0.0.1"})).json()
    assert created["ssh_username"] == "root"
    assert created["ssh_port"] == 22

    resp = await client.get("/api/systems")
    assert resp.json()[0]["ssh_username"] == "root"
    assert resp.json()[0]["ssh_port"] == 22


@pytest.mark.asyncio
async def test_system_ssh_defaults_can_be_overridden_or_cleared(client):
    await _login_admin(client)
    created = (await client.post("/api/systems", json={"name": "Maison", "url": "10.0.0.1"})).json()

    resp = await client.patch(f"/api/systems/{created['id']}", json={"ssh_username": "pi", "ssh_port": 2222})
    assert resp.status_code == 200
    assert resp.json()["ssh_username"] == "pi"
    assert resp.json()["ssh_port"] == 2222

    # Explicitly clearing opts a system back out of showing the door icon.
    resp = await client.patch(f"/api/systems/{created['id']}", json={"ssh_username": None, "ssh_port": None})
    assert resp.status_code == 200
    assert resp.json()["ssh_username"] is None
    assert resp.json()["ssh_port"] is None


@pytest.mark.asyncio
async def test_system_ssh_fields_can_be_set_at_creation(client):
    await _login_admin(client)
    resp = await client.post("/api/systems", json={
        "name": "Chalet", "url": "10.0.0.2", "ssh_username": "pi", "ssh_port": 2200,
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["ssh_username"] == "pi"
    assert resp.json()["ssh_port"] == 2200


@pytest.mark.asyncio
async def test_update_missing_system_404(client):
    await _login_admin(client)
    resp = await client.patch("/api/systems/nope", json={"name": "X"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_system(client):
    await _login_admin(client)
    created = (await client.post("/api/systems", json={"name": "Maison", "url": "10.0.0.1"})).json()
    resp = await client.delete(f"/api/systems/{created['id']}")
    assert resp.status_code == 204
    resp = await client.get("/api/systems")
    assert resp.json() == []


@pytest.mark.asyncio
async def test_delete_missing_system_404(client):
    await _login_admin(client)
    resp = await client.delete("/api/systems/nope")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_viewer_can_list_but_not_mutate_systems(client):
    await _login_admin(client)
    await client.post("/api/systems", json={"name": "Maison", "url": "10.0.0.1"})
    await _create_viewer(client)  # default viewer has no settings_manage
    await _login(client, "bob", "viewerpass1")

    resp = await client.get("/api/systems")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = await client.post("/api/systems", json={"name": "Chalet", "url": "10.0.0.2"})
    assert resp.status_code == 403
    resp = await client.patch("/api/systems/maison", json={"name": "X"})
    assert resp.status_code == 403
    resp = await client.delete("/api/systems/maison")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_with_settings_manage_can_mutate_systems(client):
    await _login_admin(client)
    await _create_viewer(client, permissions=["settings_manage"])
    await _login(client, "bob", "viewerpass1")

    resp = await client.post("/api/systems", json={"name": "Maison", "url": "10.0.0.1"})
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_systems_require_auth(client):
    resp = await client.get("/api/systems")
    assert resp.status_code == 401
