import pytest


@pytest.mark.asyncio
async def test_lockout_after_repeated_failed_logins(client):
    for _ in range(5):
        resp = await client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401

    # 6th attempt is locked out even with the *correct* password
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


@pytest.mark.asyncio
async def test_lockout_is_per_username(client):
    for _ in range(5):
        await client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})

    # a different (nonexistent) username is unaffected
    resp = await client.post("/api/auth/login", json={"username": "someoneelse", "password": "whatever"})
    assert resp.status_code == 401  # rejected for bad credentials, not locked out


@pytest.mark.asyncio
async def test_successful_login_resets_failure_count(client):
    for _ in range(4):
        await client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})

    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    assert resp.status_code == 200

    # counter was reset by the success, so this single failure doesn't lock
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401
