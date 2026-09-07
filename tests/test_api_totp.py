import pytest

from app.totp import totp_now


async def _login_admin(client):
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_login_works_normally_when_2fa_not_enabled(client):
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    assert resp.status_code == 200
    assert "token" in resp.json()


@pytest.mark.asyncio
async def test_enroll_then_confirm_enables_2fa(client):
    await _login_admin(client)
    resp = await client.post("/api/auth/totp/enroll")
    assert resp.status_code == 200
    data = resp.json()
    assert "secret" in data and "otpauth_uri" in data
    assert data["otpauth_uri"].startswith("otpauth://totp/")

    me_before = (await client.get("/api/auth/me")).json()
    assert me_before["totp_enabled"] is False

    code = totp_now(data["secret"])
    resp2 = await client.post("/api/auth/totp/confirm", json={"code": code})
    assert resp2.status_code == 200

    me_after = (await client.get("/api/auth/me")).json()
    assert me_after["totp_enabled"] is True


@pytest.mark.asyncio
async def test_confirm_with_wrong_code_does_not_enable(client):
    await _login_admin(client)
    await client.post("/api/auth/totp/enroll")
    resp = await client.post("/api/auth/totp/confirm", json={"code": "000000"})
    assert resp.status_code == 400
    me = (await client.get("/api/auth/me")).json()
    assert me["totp_enabled"] is False


@pytest.mark.asyncio
async def test_login_requires_totp_code_once_enabled(client):
    await _login_admin(client)
    secret = (await client.post("/api/auth/totp/enroll")).json()["secret"]
    await client.post("/api/auth/totp/confirm", json={"code": totp_now(secret)})
    await client.post("/api/auth/logout")

    # password alone is no longer enough
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    assert resp.status_code == 401
    data = resp.json()
    assert data.get("totp_required") is True

    # correct password + correct code succeeds
    resp2 = await client.post("/api/auth/login", json={
        "username": "admin", "password": "s3cret-pass", "totp_code": totp_now(secret),
    })
    assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_login_rejects_wrong_totp_code(client):
    await _login_admin(client)
    secret = (await client.post("/api/auth/totp/enroll")).json()["secret"]
    await client.post("/api/auth/totp/confirm", json={"code": totp_now(secret)})
    await client.post("/api/auth/logout")

    resp = await client.post("/api/auth/login", json={
        "username": "admin", "password": "s3cret-pass", "totp_code": "000000",
    })
    assert resp.status_code == 401
    assert "totp_required" not in resp.json()


@pytest.mark.asyncio
async def test_missing_totp_prompt_does_not_count_against_lockout(client):
    await _login_admin(client)
    secret = (await client.post("/api/auth/totp/enroll")).json()["secret"]
    await client.post("/api/auth/totp/confirm", json={"code": totp_now(secret)})
    await client.post("/api/auth/logout")

    # request the code prompt 4 times (no code given) - should not lock the account
    for _ in range(4):
        resp = await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
        assert resp.status_code == 401
        assert resp.json().get("totp_required") is True

    # a valid login should still succeed (not locked out)
    resp = await client.post("/api/auth/login", json={
        "username": "admin", "password": "s3cret-pass", "totp_code": totp_now(secret),
    })
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_disable_requires_correct_password(client):
    await _login_admin(client)
    secret = (await client.post("/api/auth/totp/enroll")).json()["secret"]
    await client.post("/api/auth/totp/confirm", json={"code": totp_now(secret)})

    resp = await client.post("/api/auth/totp/disable", json={"password": "wrong"})
    assert resp.status_code == 403
    assert (await client.get("/api/auth/me")).json()["totp_enabled"] is True

    resp2 = await client.post("/api/auth/totp/disable", json={"password": "s3cret-pass"})
    assert resp2.status_code == 200
    assert (await client.get("/api/auth/me")).json()["totp_enabled"] is False


@pytest.mark.asyncio
async def test_disabling_totp_removes_login_requirement(client):
    await _login_admin(client)
    secret = (await client.post("/api/auth/totp/enroll")).json()["secret"]
    await client.post("/api/auth/totp/confirm", json={"code": totp_now(secret)})
    await client.post("/api/auth/totp/disable", json={"password": "s3cret-pass"})
    await client.post("/api/auth/logout")

    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_confirm_returns_recovery_codes(client):
    await _login_admin(client)
    secret = (await client.post("/api/auth/totp/enroll")).json()["secret"]
    resp = await client.post("/api/auth/totp/confirm", json={"code": totp_now(secret)})
    data = resp.json()
    assert len(data["recovery_codes"]) == 8
    for code in data["recovery_codes"]:
        assert len(code) == 9  # "XXXX-XXXX"
        assert code[4] == "-"
    assert len(set(data["recovery_codes"])) == 8  # all distinct


@pytest.mark.asyncio
async def test_login_with_recovery_code_succeeds_and_consumes_it(client):
    await _login_admin(client)
    secret = (await client.post("/api/auth/totp/enroll")).json()["secret"]
    codes = (await client.post("/api/auth/totp/confirm", json={"code": totp_now(secret)})).json()["recovery_codes"]
    await client.post("/api/auth/logout")

    code = codes[0]
    resp = await client.post("/api/auth/login", json={
        "username": "admin", "password": "s3cret-pass", "totp_code": code,
    })
    assert resp.status_code == 200

    # the same code cannot be reused
    await client.post("/api/auth/logout")
    resp2 = await client.post("/api/auth/login", json={
        "username": "admin", "password": "s3cret-pass", "totp_code": code,
    })
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_login_with_recovery_code_counts_remaining(client):
    await _login_admin(client)
    secret = (await client.post("/api/auth/totp/enroll")).json()["secret"]
    codes = (await client.post("/api/auth/totp/confirm", json={"code": totp_now(secret)})).json()["recovery_codes"]

    me = (await client.get("/api/auth/me")).json()
    assert me["totp_recovery_codes_remaining"] == 8

    await client.post("/api/auth/logout")
    await client.post("/api/auth/login", json={
        "username": "admin", "password": "s3cret-pass", "totp_code": codes[0],
    })
    me2 = (await client.get("/api/auth/me")).json()
    assert me2["totp_recovery_codes_remaining"] == 7


@pytest.mark.asyncio
async def test_malformed_recovery_code_is_rejected(client):
    await _login_admin(client)
    secret = (await client.post("/api/auth/totp/enroll")).json()["secret"]
    await client.post("/api/auth/totp/confirm", json={"code": totp_now(secret)})
    await client.post("/api/auth/logout")

    resp = await client.post("/api/auth/login", json={
        "username": "admin", "password": "s3cret-pass", "totp_code": "ZZZZ-ZZZZ",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_disabling_totp_clears_recovery_codes(client):
    await _login_admin(client)
    secret = (await client.post("/api/auth/totp/enroll")).json()["secret"]
    codes = (await client.post("/api/auth/totp/confirm", json={"code": totp_now(secret)})).json()["recovery_codes"]
    await client.post("/api/auth/totp/disable", json={"password": "s3cret-pass"})

    # re-enroll from scratch with a new secret
    secret2 = (await client.post("/api/auth/totp/enroll")).json()["secret"]
    await client.post("/api/auth/totp/confirm", json={"code": totp_now(secret2)})
    await client.post("/api/auth/logout")

    # an old recovery code from before the disable/re-enroll no longer works
    resp = await client.post("/api/auth/login", json={
        "username": "admin", "password": "s3cret-pass", "totp_code": codes[0],
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_regenerate_recovery_codes_invalidates_old_ones(client):
    await _login_admin(client)
    secret = (await client.post("/api/auth/totp/enroll")).json()["secret"]
    old_codes = (await client.post("/api/auth/totp/confirm", json={"code": totp_now(secret)})).json()["recovery_codes"]

    resp = await client.post("/api/auth/totp/recovery-codes/regenerate", json={"password": "wrong"})
    assert resp.status_code == 403

    resp2 = await client.post("/api/auth/totp/recovery-codes/regenerate", json={"password": "s3cret-pass"})
    assert resp2.status_code == 200
    new_codes = resp2.json()["recovery_codes"]
    assert len(new_codes) == 8
    assert set(new_codes).isdisjoint(old_codes)

    await client.post("/api/auth/logout")
    resp3 = await client.post("/api/auth/login", json={
        "username": "admin", "password": "s3cret-pass", "totp_code": old_codes[0],
    })
    assert resp3.status_code == 401

    resp4 = await client.post("/api/auth/login", json={
        "username": "admin", "password": "s3cret-pass", "totp_code": new_codes[0],
    })
    assert resp4.status_code == 200


@pytest.mark.asyncio
async def test_regenerate_requires_totp_enabled(client):
    await _login_admin(client)
    resp = await client.post("/api/auth/totp/recovery-codes/regenerate", json={"password": "s3cret-pass"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_user_list_shows_totp_status(client):
    await _login_admin(client)
    secret = (await client.post("/api/auth/totp/enroll")).json()["secret"]
    await client.post("/api/auth/totp/confirm", json={"code": totp_now(secret)})

    resp = await client.get("/api/users")
    assert resp.status_code == 200
    admin_row = next(u for u in resp.json() if u["username"] == "admin")
    assert admin_row["totp_enabled"] is True
