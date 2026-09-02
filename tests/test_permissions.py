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
async def test_default_viewer_has_ptz_control_and_recordings_download(client):
    await _login_admin(client)
    user = await _create_viewer(client)
    assert user["permissions"] == ["ptz_control", "recordings_download"]


@pytest.mark.asyncio
async def test_me_reports_effective_permissions(client):
    await _login_admin(client)
    resp = await client.get("/api/auth/me")
    data = resp.json()
    assert data["role"] == "admin"
    assert set(data["permissions"]) == {
        "cameras_manage", "ptz_control", "recordings_delete", "recordings_download", "settings_manage",
    }

    await _create_viewer(client)
    await _login(client, "bob", "viewerpass1")
    resp = await client.get("/api/auth/me")
    data = resp.json()
    assert data["permissions"] == ["ptz_control", "recordings_download"]


@pytest.mark.asyncio
async def test_viewer_without_cameras_manage_cannot_create_camera(client):
    await _login_admin(client)
    await _create_viewer(client)
    await _login(client, "bob", "viewerpass1")
    resp = await client.post("/api/cameras", json={"name": "Cam", "source_type": "test", "url": "test:pattern"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_granted_cameras_manage_can_create_camera(client):
    await _login_admin(client)
    await _create_viewer(client, permissions=["ptz_control", "cameras_manage"])
    await _login(client, "bob", "viewerpass1")
    resp = await client.post("/api/cameras", json={"name": "Cam", "source_type": "test", "url": "test:pattern"})
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_admin_can_grant_and_revoke_permissions_via_patch(client):
    await _login_admin(client)
    await _create_viewer(client)
    resp = await client.patch("/api/users/bob", json={"permissions": ["settings_manage"]})
    assert resp.status_code == 200
    assert resp.json()["permissions"] == ["settings_manage"]

    await _login(client, "bob", "viewerpass1")
    # settings_manage granted -> settings PATCH allowed
    resp = await client.patch("/api/settings", json={"retention_days": 30})
    assert resp.status_code == 200
    # ptz_control was revoked by the PATCH above (replaced the whole list)
    resp = await client.post("/api/cameras/does-not-exist/ptz/stop")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_without_recordings_delete_cannot_delete(client):
    await _login_admin(client)
    await _create_viewer(client)
    await _login(client, "bob", "viewerpass1")
    resp = await client.delete("/api/cameras/whatever/recordings/2024-01-01_00-00-00.mp4")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_without_recordings_download_cannot_download(client):
    await _login_admin(client)
    await _create_viewer(client, permissions=["ptz_control"])  # recordings_download withheld
    await _login(client, "bob", "viewerpass1")
    resp = await client.get("/api/cameras/whatever/recordings/2024-01-01_00-00-00.mp4/download")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_without_recordings_download_can_still_watch_inline(client):
    # The download permission only gates the dedicated /download route - the
    # plain playback route (used by the <video> tag) stays open to any
    # authenticated user, same as before this permission existed. A 404
    # here (camera/file genuinely absent) rather than 403 proves the
    # permission check never ran for this route.
    await _login_admin(client)
    await _create_viewer(client, permissions=["ptz_control"])
    await _login(client, "bob", "viewerpass1")
    resp = await client.get("/api/cameras/whatever/recordings/2024-01-01_00-00-00.mp4")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_viewer_with_recordings_download_reaches_download_route(client):
    # Default viewer permissions include recordings_download - a 404 for a
    # nonexistent camera (rather than 403) proves the permission check
    # passed and the handler itself ran.
    await _login_admin(client)
    await _create_viewer(client)
    await _login(client, "bob", "viewerpass1")
    resp = await client.get("/api/cameras/whatever/recordings/2024-01-01_00-00-00.mp4/download")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_viewer_without_settings_manage_cannot_view_or_edit_settings(client):
    await _login_admin(client)
    await _create_viewer(client)
    await _login(client, "bob", "viewerpass1")
    resp = await client.get("/api/settings")
    assert resp.status_code == 403
    resp = await client.patch("/api/settings", json={"retention_days": 30})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_bypasses_permission_checks_regardless_of_stored_list(client):
    await _login_admin(client)
    # admin's own stored permissions list is irrelevant/empty by default,
    # but every check must still pass because role == admin.
    resp = await client.get("/api/settings")
    assert resp.status_code == 200
    resp = await client.post("/api/cameras", json={"name": "Cam", "source_type": "test", "url": "test:pattern"})
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_a_delegated_viewer_still_cannot_manage_users(client):
    # cameras_manage/settings_manage/etc. are deliberately separate from
    # user management, which stays admin-only no matter what permissions
    # a viewer is granted - this is the anti-escalation guarantee.
    await _login_admin(client)
    await _create_viewer(client, permissions=["cameras_manage", "ptz_control", "recordings_delete", "settings_manage"])
    await _login(client, "bob", "viewerpass1")
    resp = await client.get("/api/users")
    assert resp.status_code == 403
    resp = await client.post("/api/users", json={"username": "eve", "password": "whatever1", "role": "viewer"})
    assert resp.status_code == 403
