import pytest

from app.notification_settings_store import NotificationSettingsStore
from app.notifier import Notifier


class FakeResponse:
    def raise_for_status(self):
        pass


class FakeAsyncClient:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None):
        FakeAsyncClient.calls.append((url, json))
        return FakeResponse()


@pytest.fixture(autouse=True)
def _reset_fake_client():
    FakeAsyncClient.calls = []
    yield
    FakeAsyncClient.calls = []


@pytest.mark.asyncio
async def test_notify_does_nothing_when_nothing_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr("app.notifier.httpx.AsyncClient", FakeAsyncClient)
    store = NotificationSettingsStore(tmp_path / "notifications.yaml")
    notifier = Notifier(store)
    await notifier.notify(event="test", title="t", message="m", dedupe_key="k")
    assert FakeAsyncClient.calls == []


@pytest.mark.asyncio
async def test_webhook_is_called_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr("app.notifier.httpx.AsyncClient", FakeAsyncClient)
    store = NotificationSettingsStore(tmp_path / "notifications.yaml")
    store.update({"webhook_enabled": True, "webhook_url": "https://example.com/hook"})
    notifier = Notifier(store)
    await notifier.notify(event="test", title="Titre", message="Message", dedupe_key="k")
    assert len(FakeAsyncClient.calls) == 1
    url, payload = FakeAsyncClient.calls[0]
    assert url == "https://example.com/hook"
    assert payload["event"] == "test"
    assert payload["title"] == "Titre"


@pytest.mark.asyncio
async def test_webhook_failure_does_not_raise(tmp_path, monkeypatch):
    class FailingClient(FakeAsyncClient):
        async def post(self, url, json=None):
            raise RuntimeError("boom")

    monkeypatch.setattr("app.notifier.httpx.AsyncClient", FailingClient)
    store = NotificationSettingsStore(tmp_path / "notifications.yaml")
    store.update({"webhook_enabled": True, "webhook_url": "https://example.com/hook"})
    notifier = Notifier(store)
    await notifier.notify(event="test", title="t", message="m", dedupe_key="k")  # must not raise


@pytest.mark.asyncio
async def test_email_is_sent_when_enabled(tmp_path, monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=10):
            sent.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            sent.append(("starttls",))

        def login(self, user, password):
            sent.append(("login", user, password))

        def send_message(self, msg):
            sent.append(("send", str(msg["Subject"]), str(msg["To"])))

    monkeypatch.setattr("app.notifier.smtplib.SMTP", FakeSMTP)
    store = NotificationSettingsStore(tmp_path / "notifications.yaml")
    store.update({
        "email_enabled": True,
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "user",
        "smtp_password": "pass",
        "smtp_to": "dest@example.com",
    })
    notifier = Notifier(store)
    await notifier.notify(event="test", title="Alerte", message="Contenu", dedupe_key="k")

    assert ("connect", "smtp.example.com", 587) in sent
    assert ("starttls",) in sent
    assert ("login", "user", "pass") in sent
    assert any(s[0] == "send" and s[1] == "Alerte" for s in sent)


@pytest.mark.asyncio
async def test_cooldown_suppresses_repeated_notifications(tmp_path, monkeypatch):
    monkeypatch.setattr("app.notifier.httpx.AsyncClient", FakeAsyncClient)
    store = NotificationSettingsStore(tmp_path / "notifications.yaml")
    store.update({"webhook_enabled": True, "webhook_url": "https://example.com/hook"})
    notifier = Notifier(store)
    await notifier.notify(event="disk_low", title="t", message="m", dedupe_key="disk_low", cooldown_seconds=3600)
    await notifier.notify(event="disk_low", title="t", message="m", dedupe_key="disk_low", cooldown_seconds=3600)
    assert len(FakeAsyncClient.calls) == 1  # second call suppressed by cooldown


@pytest.mark.asyncio
async def test_notify_motion_respects_toggle(tmp_path, monkeypatch):
    monkeypatch.setattr("app.notifier.httpx.AsyncClient", FakeAsyncClient)
    store = NotificationSettingsStore(tmp_path / "notifications.yaml")
    store.update({"webhook_enabled": True, "webhook_url": "https://example.com/hook", "notify_on_motion": False})
    notifier = Notifier(store)
    await notifier.notify_motion("cam1", "Garage")
    assert FakeAsyncClient.calls == []

    store.update({"notify_on_motion": True})
    await notifier.notify_motion("cam1", "Garage")
    assert len(FakeAsyncClient.calls) == 1
