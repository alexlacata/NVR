import yaml

from app.notification_settings_store import NotificationSettingsStore
from app.secrets_crypto import SecretsCipher


def test_get_returns_defaults_when_no_file(tmp_path):
    store = NotificationSettingsStore(tmp_path / "notifications.yaml")
    settings = store.get()
    assert settings.webhook_enabled is False
    assert settings.email_enabled is False
    assert settings.notify_on_motion is True


def test_update_persists_a_partial_patch_without_touching_other_fields(tmp_path):
    store = NotificationSettingsStore(tmp_path / "notifications.yaml")
    updated = store.update({"webhook_enabled": True, "webhook_url": "https://example.com/hook"})
    assert updated.webhook_enabled is True
    assert updated.webhook_url == "https://example.com/hook"

    # A key simply absent from the patch (not sent by the caller) must
    # leave the existing value alone.
    updated2 = store.update({"notify_on_motion": False})
    assert updated2.webhook_enabled is True
    assert updated2.webhook_url == "https://example.com/hook"
    assert updated2.notify_on_motion is False

    reloaded = NotificationSettingsStore(tmp_path / "notifications.yaml").get()
    assert reloaded.webhook_enabled is True
    assert reloaded.notify_on_motion is False


def test_update_with_explicit_none_clears_the_field(tmp_path):
    store = NotificationSettingsStore(tmp_path / "notifications.yaml")
    store.update({"webhook_enabled": True, "webhook_url": "https://example.com/hook"})

    cleared = store.update({"webhook_url": None})
    assert cleared.webhook_url is None
    assert cleared.webhook_enabled is True
    assert NotificationSettingsStore(tmp_path / "notifications.yaml").get().webhook_url is None


def test_update_can_explicitly_set_a_bool_to_false(tmp_path):
    store = NotificationSettingsStore(tmp_path / "notifications.yaml")
    store.update({"notify_on_disk_low": True})
    updated = store.update({"notify_on_disk_low": False})
    assert updated.notify_on_disk_low is False


def test_smtp_password_is_encrypted_at_rest(tmp_path):
    path = tmp_path / "notifications.yaml"
    cipher = SecretsCipher("a-secret-key")
    store = NotificationSettingsStore(path, cipher)
    store.update({"smtp_password": "hunter2"})

    on_disk = yaml.safe_load(path.read_text())
    assert on_disk["smtp_password"] != "hunter2"
    assert cipher.decrypt(on_disk["smtp_password"]) == "hunter2"

    # transparently decrypted for the store's own callers
    assert store.get().smtp_password == "hunter2"


def test_smtp_password_roundtrips_across_store_instances(tmp_path):
    path = tmp_path / "notifications.yaml"
    cipher = SecretsCipher("a-secret-key")
    NotificationSettingsStore(path, cipher).update({"smtp_password": "hunter2"})
    reopened = NotificationSettingsStore(path, cipher)
    assert reopened.get().smtp_password == "hunter2"


def test_without_a_cipher_smtp_password_stays_plaintext(tmp_path):
    path = tmp_path / "notifications.yaml"
    NotificationSettingsStore(path).update({"smtp_password": "hunter2"})
    on_disk = yaml.safe_load(path.read_text())
    assert on_disk["smtp_password"] == "hunter2"


def test_a_preexisting_plaintext_password_still_works_once_a_cipher_is_added(tmp_path):
    path = tmp_path / "notifications.yaml"
    NotificationSettingsStore(path).update({"smtp_password": "hunter2"})

    upgraded = NotificationSettingsStore(path, SecretsCipher("a-secret-key"))
    assert upgraded.get().smtp_password == "hunter2"
