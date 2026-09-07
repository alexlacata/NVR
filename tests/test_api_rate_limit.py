import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings, get_settings
from app.main import create_app


@pytest.fixture()
def tight_app(tmp_path, monkeypatch):
    settings = Settings(
        data_dir=tmp_path,
        admin_username="admin",
        admin_password="s3cret-pass",
        secret_key="test-secret-key",
        rate_limit_max_requests=3,
        rate_limit_window_seconds=60,
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings, raising=False)
    get_settings.cache_clear()

    import app.main as main_module

    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    return create_app()


@pytest.fixture()
async def tight_client(tight_app):
    async with tight_app.router.lifespan_context(tight_app):
        transport = ASGITransport(app=tight_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.mark.asyncio
async def test_authenticated_requests_are_rate_limited_per_account(tight_client):
    resp = await tight_client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    assert resp.status_code == 200

    for _ in range(3):
        resp = await tight_client.get("/api/auth/me")
        assert resp.status_code == 200

    resp = await tight_client.get("/api/auth/me")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


@pytest.mark.asyncio
async def test_rate_limit_does_not_apply_to_static_files(tight_client):
    for _ in range(6):
        resp = await tight_client.get("/login.html")
        assert resp.status_code in (200, 404)


@pytest.mark.asyncio
async def test_unauthenticated_requests_are_rate_limited_per_ip(tight_client):
    for _ in range(3):
        resp = await tight_client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401

    resp = await tight_client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_different_accounts_have_independent_budgets(tight_client):
    login = await tight_client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    assert login.status_code == 200

    # creating bob spends 1 of admin's 3-request budget
    resp = await tight_client.post("/api/users", json={"username": "bob", "password": "viewerpass1", "role": "viewer"})
    assert resp.status_code == 201

    for _ in range(2):
        resp = await tight_client.get("/api/auth/me")
        assert resp.status_code == 200
    resp = await tight_client.get("/api/auth/me")
    assert resp.status_code == 429

    # bob has his own budget (and identity), unaffected by admin's being
    # spent - clear the cookie jar first, otherwise this request would
    # still authenticate (and be counted) as admin's still-valid session
    tight_client.cookies.clear()
    bob_login = await tight_client.post("/api/auth/login", json={"username": "bob", "password": "viewerpass1"})
    assert bob_login.status_code == 200
