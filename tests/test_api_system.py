import pytest


async def _login_admin(client):
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_system_info_requires_auth(client):
    resp = await client.get("/api/system")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_system_info_includes_health_fields(client):
    await _login_admin(client)
    resp = await client.get("/api/system")
    assert resp.status_code == 200
    data = resp.json()
    assert "disk_free_percent" in data
    assert "cpu_load_percent" in data
    assert "memory_percent" in data
    assert "cpu_temperature_celsius" in data
    assert data["video_encoder"] in ("hardware", "software")
