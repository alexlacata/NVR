import pytest

from app.auth import COOKIE_NAME


async def _login_admin(client, headers=None):
    resp = await client.post(
        "/api/auth/login", json={"username": "admin", "password": "s3cret-pass"}, headers=headers or {},
    )
    assert resp.status_code == 200
    return resp.json()["token"]


@pytest.mark.asyncio
async def test_login_creates_a_listed_session(client):
    await _login_admin(client, headers={"User-Agent": "TestBrowser/1.0"})
    resp = await client.get("/api/auth/sessions")
    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) == 1
    assert sessions[0]["user_agent"] == "TestBrowser/1.0"
    assert sessions[0]["current"] is True


@pytest.mark.asyncio
async def test_multiple_logins_create_multiple_sessions(client):
    await _login_admin(client, headers={"User-Agent": "Browser1"})
    await _login_admin(client, headers={"User-Agent": "Browser2"})
    resp = await client.get("/api/auth/sessions")
    sessions = resp.json()
    assert len(sessions) == 2
    # the most recent login's cookie is what "client" now sends, so it's "current"
    current = [s for s in sessions if s["current"]]
    assert len(current) == 1
    assert current[0]["user_agent"] == "Browser2"


@pytest.mark.asyncio
async def test_logout_revokes_current_session(client):
    token = await _login_admin(client)
    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 200

    # the token is no longer valid even as a bearer token, since the
    # session was revoked server-side, not just the cookie cleared
    resp2 = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_revoke_specific_session(client):
    await _login_admin(client, headers={"User-Agent": "Browser1"})
    token2 = await _login_admin(client, headers={"User-Agent": "Browser2"})  # client now uses this cookie

    sessions = (await client.get("/api/auth/sessions")).json()
    other_session = next(s for s in sessions if not s["current"])

    resp = await client.delete(f"/api/auth/sessions/{other_session['jti']}")
    assert resp.status_code == 200

    remaining = (await client.get("/api/auth/sessions")).json()
    assert len(remaining) == 1
    assert remaining[0]["current"] is True

    # the current session (Browser2) is unaffected
    resp2 = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token2}"})
    assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_cannot_revoke_someone_elses_session(client):
    await _login_admin(client)
    resp = await client.post("/api/users", json={"username": "bob", "password": "viewerpass1", "role": "viewer"})
    assert resp.status_code == 201

    admin_sessions = (await client.get("/api/auth/sessions")).json()
    admin_jti = admin_sessions[0]["jti"]

    await client.post("/api/auth/login", json={"username": "bob", "password": "viewerpass1"})
    resp = await client.delete(f"/api/auth/sessions/{admin_jti}")
    assert resp.status_code == 404  # not bob's session - not found, not revoked


@pytest.mark.asyncio
async def test_revoke_unknown_session_404(client):
    await _login_admin(client)
    resp = await client.delete("/api/auth/sessions/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_changing_password_revokes_other_sessions(client):
    token1 = await _login_admin(client, headers={"User-Agent": "Browser1"})
    await _login_admin(client, headers={"User-Agent": "Browser2"})  # client now uses this session

    resp = await client.patch("/api/auth/password", json={
        "current_password": "s3cret-pass", "new_password": "newpassword123",
    })
    assert resp.status_code == 200

    # Browser1's session is revoked - checked via the Bearer header with the
    # client's own cookie jar cleared first, since the cookie (still valid,
    # Browser2's) would otherwise win and mask a stale Bearer token.
    saved_cookie = client.cookies.get(COOKIE_NAME)
    client.cookies.clear()
    resp2 = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token1}"})
    assert resp2.status_code == 401

    # ...but the session that made this very request (Browser2) survives
    client.cookies.set(COOKIE_NAME, saved_cookie)
    resp3 = await client.get("/api/auth/me")
    assert resp3.status_code == 200


@pytest.mark.asyncio
async def test_sessions_require_auth(client):
    resp = await client.get("/api/auth/sessions")
    assert resp.status_code == 401
