import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings, get_settings
from app.main import create_app


@pytest.fixture()
def app_settings(tmp_path, monkeypatch):
    settings = Settings(
        data_dir=tmp_path,
        admin_username="admin",
        admin_password="s3cret-pass",
        secret_key="test-secret-key",
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings, raising=False)
    get_settings.cache_clear()

    def _get():
        return settings

    import app.main as main_module
    monkeypatch.setattr(main_module, "get_settings", _get)
    return settings


@pytest.fixture()
def app(app_settings):
    return create_app()


@pytest.fixture()
async def client(app):
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
