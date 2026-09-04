from app.config import Settings


def test_run_server_passes_ssl_paths_when_configured(monkeypatch, tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        host="127.0.0.1",
        port=8443,
        ssl_certfile="/etc/nvr/cert.pem",
        ssl_keyfile="/etc/nvr/key.pem",
    )
    monkeypatch.setattr("app.main.get_settings", lambda: settings)

    calls = []
    fake_uvicorn = type("FakeUvicorn", (), {"run": staticmethod(lambda *a, **kw: calls.append((a, kw)))})
    monkeypatch.setitem(__import__("sys").modules, "uvicorn", fake_uvicorn)

    from app.main import run_server
    run_server()

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("app.main:app",)
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8443
    assert kwargs["ssl_certfile"] == "/etc/nvr/cert.pem"
    assert kwargs["ssl_keyfile"] == "/etc/nvr/key.pem"


def test_run_server_omits_ssl_when_not_configured(monkeypatch, tmp_path):
    settings = Settings(data_dir=tmp_path, host="0.0.0.0", port=8000)
    monkeypatch.setattr("app.main.get_settings", lambda: settings)

    calls = []
    fake_uvicorn = type("FakeUvicorn", (), {"run": staticmethod(lambda *a, **kw: calls.append((a, kw)))})
    monkeypatch.setitem(__import__("sys").modules, "uvicorn", fake_uvicorn)

    from app.main import run_server
    run_server()

    assert len(calls) == 1
    _, kwargs = calls[0]
    assert kwargs["ssl_certfile"] is None
    assert kwargs["ssl_keyfile"] is None
