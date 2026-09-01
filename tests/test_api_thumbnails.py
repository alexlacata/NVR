import pytest


async def _login_and_create_camera(client, cam_id="cam1"):
    await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    resp = await client.post(
        "/api/cameras",
        json={"id": cam_id, "name": "Cam 1", "source_type": "test", "url": "test:pattern"},
    )
    return resp


@pytest.mark.asyncio
async def test_list_thumbnails_empty_when_none_exist(client, app_settings):
    await _login_and_create_camera(client)
    resp = await client.get("/api/cameras/cam1/thumbnails")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_and_get_thumbnail(client, app_settings):
    await _login_and_create_camera(client)
    thumb_dir = app_settings.thumbnails_dir / "cam1"
    thumb_dir.mkdir(parents=True)
    (thumb_dir / "2026-09-01_08-00-00.jpg").write_bytes(b"\xff\xd8\xff\xd9")  # minimal jpeg-ish bytes

    resp = await client.get("/api/cameras/cam1/thumbnails?date=2026-09-01")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["time"] == "08:00:00"

    resp = await client.get("/api/cameras/cam1/thumbnails/2026-09-01_08-00-00.jpg")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert "immutable" in resp.headers["cache-control"]


@pytest.mark.asyncio
async def test_get_thumbnail_rejects_path_traversal(client, app_settings):
    await _login_and_create_camera(client)
    resp = await client.get("/api/cameras/cam1/thumbnails/..%2F..%2Fsecret.jpg")
    assert resp.status_code in (400, 404)


@pytest.mark.asyncio
async def test_recordings_at_finds_covering_segment(client, app_settings):
    await _login_and_create_camera(client)
    rec_dir = app_settings.recordings_dir / "cam1"
    rec_dir.mkdir(parents=True, exist_ok=True)
    (rec_dir / "2026-09-01_08-00-00.mp4").write_bytes(b"0")
    (rec_dir / "2026-09-01_08-10-00.mp4").write_bytes(b"0")

    resp = await client.get("/api/cameras/cam1/recordings/at?ts=2026-09-01T08:12:30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "2026-09-01_08-10-00.mp4"
    assert data["offset_seconds"] == pytest.approx(150.0)


@pytest.mark.asyncio
async def test_recordings_at_before_first_segment_snaps_to_earliest(client, app_settings):
    await _login_and_create_camera(client)
    rec_dir = app_settings.recordings_dir / "cam1"
    rec_dir.mkdir(parents=True, exist_ok=True)
    (rec_dir / "2026-09-01_08-00-00.mp4").write_bytes(b"0")

    resp = await client.get("/api/cameras/cam1/recordings/at?ts=2026-09-01T07:00:00")
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "2026-09-01_08-00-00.mp4"
    assert data["offset_seconds"] == 0


@pytest.mark.asyncio
async def test_recordings_at_no_recordings_404(client, app_settings):
    await _login_and_create_camera(client)
    resp = await client.get("/api/cameras/cam1/recordings/at?ts=2026-09-01T08:00:00")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_recordings_at_bad_timestamp_400(client, app_settings):
    await _login_and_create_camera(client)
    resp = await client.get("/api/cameras/cam1/recordings/at?ts=not-a-date")
    assert resp.status_code == 400
