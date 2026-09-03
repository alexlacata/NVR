import pytest


async def _login_admin(client):
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_users_requires_auth(client):
    resp = await client.get("/api/users")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bootstrap_admin_is_listed(client):
    await _login_admin(client)
    resp = await client.get("/api/users")
    assert resp.status_code == 200
    users = resp.json()
    assert len(users) == 1
    assert users[0]["username"] == "admin"
    assert users[0]["role"] == "admin"
    assert "password_hash" not in users[0]


@pytest.mark.asyncio
async def test_admin_can_create_user(client):
    await _login_admin(client)
    resp = await client.post("/api/users", json={"username": "bob", "password": "viewerpass1", "role": "viewer"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "bob"
    assert data["role"] == "viewer"


@pytest.mark.asyncio
async def test_duplicate_username_rejected(client):
    await _login_admin(client)
    payload = {"username": "bob", "password": "viewerpass1", "role": "viewer"}
    resp = await client.post("/api/users", json=payload)
    assert resp.status_code == 201
    resp = await client.post("/api/users", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_weak_password_rejected(client):
    await _login_admin(client)
    resp = await client.post("/api/users", json={"username": "bob", "password": "short", "role": "viewer"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_viewer_cannot_manage_users(client):
    await _login_admin(client)
    await client.post("/api/users", json={"username": "bob", "password": "viewerpass1", "role": "viewer"})
    # switch session to the viewer
    resp = await client.post("/api/auth/login", json={"username": "bob", "password": "viewerpass1"})
    assert resp.status_code == 200

    resp = await client.get("/api/users")
    assert resp.status_code == 403
    resp = await client.post("/api/users", json={"username": "eve", "password": "whatever1", "role": "viewer"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_can_view_cameras_but_not_create(client):
    await _login_admin(client)
    await client.post("/api/users", json={"username": "bob", "password": "viewerpass1", "role": "viewer"})
    await client.post("/api/auth/login", json={"username": "bob", "password": "viewerpass1"})

    resp = await client.get("/api/cameras")
    assert resp.status_code == 200

    resp = await client.post("/api/cameras", json={"name": "Cam", "source_type": "test", "url": "test:pattern"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cannot_delete_self(client):
    await _login_admin(client)
    resp = await client.delete("/api/users/admin")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_deleting_one_of_two_admins_is_allowed(client):
    await _login_admin(client)
    await client.post("/api/users", json={"username": "root2", "password": "adminpass1", "role": "admin"})
    await client.post("/api/auth/login", json={"username": "root2", "password": "adminpass1"})
    resp = await client.delete("/api/users/admin")
    assert resp.status_code == 204  # root2 is still an admin, so this is fine


@pytest.mark.asyncio
async def test_cannot_demote_the_last_admin(client):
    # self-delete is blocked separately (see test_cannot_delete_self), but
    # nothing stops a lone admin from demoting themselves via PATCH - the
    # store's last-admin guard must catch that instead.
    await _login_admin(client)
    resp = await client.patch("/api/users/admin", json={"role": "viewer"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_admin_can_delete_other_user(client):
    await _login_admin(client)
    await client.post("/api/users", json={"username": "bob", "password": "viewerpass1", "role": "viewer"})
    resp = await client.delete("/api/users/bob")
    assert resp.status_code == 204
    resp = await client.get("/api/users")
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_update_role_and_password(client):
    await _login_admin(client)
    await client.post("/api/users", json={"username": "bob", "password": "viewerpass1", "role": "viewer"})
    resp = await client.patch("/api/users/bob", json={"role": "admin"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"

    resp = await client.patch("/api/users/bob", json={"password": "newpassword1"})
    assert resp.status_code == 200
    resp = await client.post("/api/auth/login", json={"username": "bob", "password": "newpassword1"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_update_missing_user_404(client):
    await _login_admin(client)
    resp = await client.patch("/api/users/nope", json={"role": "admin"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_self_password_change(client):
    await _login_admin(client)
    resp = await client.patch("/api/auth/password", json={
        "current_password": "s3cret-pass", "new_password": "brandnewpass1",
    })
    assert resp.status_code == 200
    # old password no longer works
    client.cookies.clear()
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    assert resp.status_code == 401
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "brandnewpass1"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_self_password_change_wrong_current_rejected(client):
    await _login_admin(client)
    resp = await client.patch("/api/auth/password", json={
        "current_password": "wrong-password", "new_password": "brandnewpass1",
    })
    # 403, not 401: the session is still valid, only the submitted current
    # password was wrong. A 401 here would make the frontend's generic
    # "401 -> redirect to login" handling swallow this error silently
    # instead of showing it in the password-change form.
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_me_returns_role(client):
    await _login_admin(client)
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "admin"
    assert data["role"] == "admin"
