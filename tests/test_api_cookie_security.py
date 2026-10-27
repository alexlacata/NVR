import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings, get_settings
from app.main import create_app


def _build_client_fixture(tmp_path, monkeypatch, **overrides):
    settings = Settings(
        data_dir=tmp_path,
        admin_username="admin",
        admin_password="s3cret-pass",
        secret_key="test-secret-key",
        **overrides,
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings, raising=False)
    get_settings.cache_clear()
    import app.main as main_module

    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    return create_app()


@pytest.mark.asyncio
async def test_session_cookie_not_secure_by_default(client):
    # Plain HTTP LAN deployment (no TLS configured at all): the cookie
    # must not be marked Secure, or the browser would never send it back
    # and login would appear to silently fail.
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie", "")
    assert "nvr_session=" in set_cookie
    assert "secure" not in set_cookie.lower()
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()


@pytest.mark.asyncio
async def test_session_cookie_secure_with_native_https(tmp_path, monkeypatch):
    app = _build_client_fixture(
        tmp_path, monkeypatch,
        ssl_certfile=str(tmp_path / "cert.pem"), ssl_keyfile=str(tmp_path / "key.pem"),
    )
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
            assert resp.status_code == 200
            assert "secure" in resp.headers.get("set-cookie", "").lower()


@pytest.mark.asyncio
async def test_session_cookie_secure_behind_tls_proxy(tmp_path, monkeypatch):
    app = _build_client_fixture(tmp_path, monkeypatch, behind_tls_proxy=True)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post("/api/auth/login", json={"username": "admin", "password": "s3cret-pass"})
            assert resp.status_code == 200
            assert "secure" in resp.headers.get("set-cookie", "").lower()
