from app.notification_settings_store import NotificationSettingsStore


def test_get_returns_defaults_when_no_file(tmp_path):
    store = NotificationSettingsStore(tmp_path / "notifications.yaml")
    settings = store.get()
    assert settings.webhook_enabled is False
    assert settings.email_enabled is False
    assert settings.notify_on_motion is True


def test_update_persists_and_ignores_none_values(tmp_path):
    store = NotificationSettingsStore(tmp_path / "notifications.yaml")
    updated = store.update({"webhook_enabled": True, "webhook_url": "https://example.com/hook"})
    assert updated.webhook_enabled is True
    assert updated.webhook_url == "https://example.com/hook"

    # a second, partial update with None fields leaves the existing ones untouched
    updated2 = store.update({"webhook_url": None, "notify_on_motion": False})
    assert updated2.webhook_enabled is True
    assert updated2.webhook_url == "https://example.com/hook"
    assert updated2.notify_on_motion is False

    reloaded = NotificationSettingsStore(tmp_path / "notifications.yaml").get()
    assert reloaded.webhook_enabled is True
    assert reloaded.notify_on_motion is False


def test_update_can_explicitly_set_a_bool_to_false(tmp_path):
    store = NotificationSettingsStore(tmp_path / "notifications.yaml")
    store.update({"notify_on_disk_low": True})
    updated = store.update({"notify_on_disk_low": False})
    assert updated.notify_on_disk_low is False
