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
async def test_security_headers_present_on_api_response(client):
    resp = await client.get("/api/auth/me")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "same-origin"
    assert "frame-ancestors 'none'" in resp.headers["content-security-policy"]
    assert resp.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=(), payment=()"


@pytest.mark.asyncio
async def test_hsts_absent_without_https(client):
    resp = await client.get("/api/auth/me")
    assert "strict-transport-security" not in resp.headers


@pytest.mark.asyncio
async def test_hsts_present_with_native_https(tmp_path, monkeypatch):
    app = _build_client_fixture(
        tmp_path, monkeypatch,
        ssl_certfile=str(tmp_path / "cert.pem"), ssl_keyfile=str(tmp_path / "key.pem"),
    )
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/auth/me")
            assert "max-age=31536000" in resp.headers["strict-transport-security"]


@pytest.mark.asyncio
async def test_hsts_present_behind_tls_proxy(tmp_path, monkeypatch):
    app = _build_client_fixture(tmp_path, monkeypatch, behind_tls_proxy=True)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/auth/me")
            assert "max-age=31536000" in resp.headers["strict-transport-security"]
