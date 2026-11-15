"""Tests de l'annuaire NVR (service separe, voir ../app.py)."""
from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

DIRECTORY_ROOT = Path(__file__).resolve().parent.parent
PASSWORD = "mot-de-passe-de-test"


@pytest.fixture
def directory(tmp_path, monkeypatch):
    # Charge par chemin sous un nom a part : `import app` designerait le
    # paquet app/ du NVR quand la suite tourne depuis la racine du depot.
    monkeypatch.setenv("DIRECTORY_PASSWORD", PASSWORD)
    monkeypatch.setenv("DIRECTORY_DATA_DIR", str(tmp_path))
    spec = importlib.util.spec_from_file_location("nvr_directory_app", DIRECTORY_ROOT / "app.py")
    module = importlib.util.module_from_spec(spec)
    # Pydantic resout les annotations differees via sys.modules.
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def make_client(directory, ip="203.0.113.10"):
    # Fixe l'adresse du visiteur comme le fait uvicorn (--proxy-headers) a
    # partir de l'en-tete pose par Caddy.
    async def from_ip(scope, receive, send):
        if scope["type"] == "http":
            scope = {**scope, "client": (ip, 50000)}
        await directory.app(scope, receive, send)

    return TestClient(from_ip, base_url="https://testserver")


def login(client, password=PASSWORD):
    return client.post("/api/login", json={"password": password})


@pytest.fixture
def client(directory):
    c = make_client(directory)
    assert login(c).status_code == 200
    return c


def test_systems_require_login(directory):
    c = make_client(directory)
    assert c.get("/api/systems").status_code == 401
    assert c.post("/api/systems", json={"name": "x", "url": "https://x"}).status_code == 401
    assert c.get("/api/session").json() == {"authenticated": False}


def test_wrong_password_rejected(directory):
    c = make_client(directory)
    assert login(c, "faux").status_code == 401
    assert c.get("/api/systems").status_code == 401


def test_session_cookie_is_httponly_and_secure(directory):
    c = make_client(directory)
    set_cookie = login(c).headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "secure" in set_cookie


def test_create_list_update_delete(client):
    created = client.post(
        "/api/systems", json={"name": "Maison", "url": "https://maison.example:8000", "notes": "garage"}
    ).json()
    assert client.get("/api/systems").json() == [created]

    updated = client.patch(f"/api/systems/{created['id']}", json={"notes": ""}).json()
    assert updated == {**created, "notes": ""}

    assert client.delete(f"/api/systems/{created['id']}").status_code == 200
    assert client.get("/api/systems").json() == []


def test_unknown_system_is_404(client):
    assert client.patch("/api/systems/inconnu", json={"name": "x"}).status_code == 404
    assert client.delete("/api/systems/inconnu").status_code == 404


@pytest.mark.parametrize("url", ["ftp://x", "file:///etc/passwd", "javascript://x"])
def test_non_http_scheme_rejected(client, url):
    assert client.post("/api/systems", json={"name": "x", "url": url}).status_code == 422
    created = client.post("/api/systems", json={"name": "x", "url": "http://ok"}).json()
    assert client.patch(f"/api/systems/{created['id']}", json={"url": url}).status_code == 422
    assert client.get("/api/systems").json() == [created]


def test_bare_address_gets_http_scheme(client):
    created = client.post("/api/systems", json={"name": "x", "url": " 192.168.1.2:8000 "}).json()
    assert created["url"] == "http://192.168.1.2:8000"
    updated = client.patch(f"/api/systems/{created['id']}", json={"url": "nvr.example"}).json()
    assert updated["url"] == "http://nvr.example"


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,x", "JaVaScRiPt:alert(1)"])
def test_stored_url_is_never_a_script_link(client, url):
    r = client.post("/api/systems", json={"name": "x", "url": url})
    assert r.status_code == 422 or r.json()["url"].startswith("http://")


def test_data_survives_restart(directory, client, tmp_path):
    created = client.post("/api/systems", json={"name": "Chalet", "url": "https://chalet.example"}).json()
    assert (tmp_path / "systems.yml").exists()
    # Un autre appareil (nouvelle session) voit la meme liste.
    other = make_client(directory, ip="198.51.100.7")
    assert login(other).status_code == 200
    assert other.get("/api/systems").json() == [created]


def test_logout_invalidates_session(client):
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/systems").status_code == 401


def test_lockout_after_too_many_failures(directory):
    c = make_client(directory)
    for _ in range(directory.MAX_ATTEMPTS):
        assert login(c, "faux").status_code == 401
    assert login(c).status_code == 429


def test_lockout_is_per_ip(directory):
    attacker = make_client(directory, ip="192.0.2.66")
    for _ in range(directory.MAX_ATTEMPTS + 2):
        login(attacker, "faux")
    assert login(attacker).status_code == 429
    owner = make_client(directory, ip="203.0.113.10")
    assert login(owner).status_code == 200


def test_lockout_expires(directory, monkeypatch):
    c = make_client(directory)
    for _ in range(directory.MAX_ATTEMPTS):
        login(c, "faux")
    assert login(c).status_code == 429
    real_time = directory.time.time
    monkeypatch.setattr(directory.time, "time", lambda: real_time() + directory.LOCKOUT_SECONDS + 1)
    assert login(c).status_code == 200


def test_successful_login_clears_failures(directory):
    c = make_client(directory)
    for _ in range(directory.MAX_ATTEMPTS - 1):
        login(c, "faux")
    assert login(c).status_code == 200
    for _ in range(directory.MAX_ATTEMPTS - 1):
        assert login(c, "faux").status_code == 401
    assert login(c).status_code == 200


def test_concurrent_creates_are_not_lost(directory, client):
    cookies = dict(client.cookies)

    def create(i):
        c = make_client(directory)
        c.cookies.update(cookies)
        assert c.post("/api/systems", json={"name": f"NVR {i}", "url": f"https://nvr{i}.example"}).status_code == 200

    threads = [threading.Thread(target=create, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(client.get("/api/systems").json()) == 20


def test_container_trusts_proxy_headers():
    # Sans ces options, uvicorn voit l'adresse de Caddy pour tout le
    # monde et le blocage anti-bruteforce devient global.
    dockerfile = (DIRECTORY_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "--proxy-headers" in dockerfile
    assert "--forwarded-allow-ips" in dockerfile
