"""Per-camera access restriction (User.allowed_camera_ids): a viewer can be
limited to a specific set of cameras, on top of (not instead of) the
existing operational permissions in test_permissions.py."""
import pytest


async def _login_admin(client):
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    assert resp.status_code == 200


async def _login(client, username, password):
    resp = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200


async def _create_camera(client, name="Cam"):
    resp = await client.post("/api/cameras", json={"name": name, "source_type": "test", "url": "test:pattern"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_viewer(client, username="bob", password="viewerpass1", allowed_camera_ids=None):
    payload = {
        "username": username, "password": password, "role": "viewer",
        "permissions": ["ptz_control", "recordings_download"],
    }
    if allowed_camera_ids is not None:
        payload["allowed_camera_ids"] = allowed_camera_ids
    resp = await client.post("/api/users", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_viewer_sees_every_camera_by_default(client):
    await _login_admin(client)
    cam_a = await _create_camera(client, "A")
    cam_b = await _create_camera(client, "B")
    await _create_viewer(client)
    await _login(client, "bob", "viewerpass1")

    resp = await client.get("/api/cameras")
    ids = {c["id"] for c in resp.json()}
    assert ids == {cam_a, cam_b}


@pytest.mark.asyncio
async def test_restricted_viewer_only_sees_allowed_cameras_in_list(client):
    await _login_admin(client)
    cam_a = await _create_camera(client, "A")
    cam_b = await _create_camera(client, "B")
    await _create_viewer(client, allowed_camera_ids=[cam_a])
    await _login(client, "bob", "viewerpass1")

    resp = await client.get("/api/cameras")
    ids = {c["id"] for c in resp.json()}
    assert ids == {cam_a}
    assert cam_b not in ids


@pytest.mark.asyncio
async def test_restricted_viewer_gets_404_for_disallowed_camera(client):
    await _login_admin(client)
    cam_a = await _create_camera(client, "A")
    cam_b = await _create_camera(client, "B")
    await _create_viewer(client, allowed_camera_ids=[cam_a])
    await _login(client, "bob", "viewerpass1")

    resp = await client.get(f"/api/cameras/{cam_a}")
    assert resp.status_code == 200
    resp = await client.get(f"/api/cameras/{cam_b}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Camera introuvable"


@pytest.mark.asyncio
async def test_restriction_blocks_media_and_ptz_and_motion_routes(client):
    await _login_admin(client)
    cam_b = await _create_camera(client, "B")
    await _create_viewer(client, allowed_camera_ids=["some-other-cam"])
    await _login(client, "bob", "viewerpass1")

    resp = await client.get(f"/api/cameras/{cam_b}/snapshot.jpg")
    assert resp.status_code == 404
    resp = await client.get(f"/api/cameras/{cam_b}/recordings")
    assert resp.status_code == 404
    resp = await client.get(f"/api/cameras/{cam_b}/recordings/2024-01-01_00-00-00.mp4")
    assert resp.status_code == 404
    resp = await client.get(f"/api/cameras/{cam_b}/recordings/2024-01-01_00-00-00.mp4/download")
    assert resp.status_code == 404
    resp = await client.get(f"/api/cameras/{cam_b}/thumbnails")
    assert resp.status_code == 404
    resp = await client.get(f"/api/cameras/{cam_b}/motion")
    assert resp.status_code == 404
    # ptz_control is granted, but the camera itself is outside the allow-list
    resp = await client.post(f"/api/cameras/{cam_b}/ptz/stop")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_restricted_viewer_with_cameras_manage_cannot_edit_disallowed_camera(client):
    await _login_admin(client)
    cam_a = await _create_camera(client, "A")
    cam_b = await _create_camera(client, "B")
    resp = await client.post("/api/users", json={
        "username": "bob", "password": "viewerpass1", "role": "viewer",
        "permissions": ["cameras_manage"], "allowed_camera_ids": [cam_a],
    })
    assert resp.status_code == 201
    await _login(client, "bob", "viewerpass1")

    resp = await client.patch(f"/api/cameras/{cam_a}", json={"name": "A renamed"})
    assert resp.status_code == 200
    resp = await client.patch(f"/api/cameras/{cam_b}", json={"name": "B renamed"})
    assert resp.status_code == 404
    resp = await client.delete(f"/api/cameras/{cam_b}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_empty_allowed_camera_ids_means_no_cameras(client):
    await _login_admin(client)
    cam_a = await _create_camera(client, "A")
    await _create_viewer(client, allowed_camera_ids=[])
    await _login(client, "bob", "viewerpass1")

    resp = await client.get("/api/cameras")
    assert resp.json() == []
    resp = await client.get(f"/api/cameras/{cam_a}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_always_sees_every_camera_regardless_of_stored_list(client):
    await _login_admin(client)
    cam_a = await _create_camera(client, "A")
    resp = await client.get("/api/cameras")
    assert {c["id"] for c in resp.json()} == {cam_a}


@pytest.mark.asyncio
async def test_admin_can_restrict_and_then_unrestrict_via_patch(client):
    await _login_admin(client)
    cam_a = await _create_camera(client, "A")
    cam_b = await _create_camera(client, "B")
    await _create_viewer(client)

    resp = await client.patch("/api/users/bob", json={"allowed_camera_ids": [cam_a]})
    assert resp.status_code == 200
    assert resp.json()["allowed_camera_ids"] == [cam_a]

    await _login(client, "bob", "viewerpass1")
    resp = await client.get("/api/cameras")
    assert {c["id"] for c in resp.json()} == {cam_a}

    await _login_admin(client)
    # Explicit null clears the restriction back to "every camera" - this is
    # the one field where None is a real, settable value rather than
    # "leave unchanged" (see UserUpdate.allowed_camera_ids).
    resp = await client.patch("/api/users/bob", json={"allowed_camera_ids": None})
    assert resp.status_code == 200
    assert resp.json()["allowed_camera_ids"] is None

    await _login(client, "bob", "viewerpass1")
    resp = await client.get("/api/cameras")
    assert {c["id"] for c in resp.json()} == {cam_a, cam_b}


@pytest.mark.asyncio
async def test_patch_without_allowed_camera_ids_leaves_restriction_untouched(client):
    await _login_admin(client)
    await _create_viewer(client, allowed_camera_ids=["cam-a"])
    resp = await client.patch("/api/users/bob", json={"permissions": ["settings_manage"]})
    assert resp.status_code == 200
    assert resp.json()["allowed_camera_ids"] == ["cam-a"]


@pytest.mark.asyncio
async def test_list_users_reports_allowed_camera_ids(client):
    await _login_admin(client)
    await _create_viewer(client, allowed_camera_ids=["cam-a", "cam-b"])
    resp = await client.get("/api/users")
    bob = next(u for u in resp.json() if u["username"] == "bob")
    assert bob["allowed_camera_ids"] == ["cam-a", "cam-b"]
