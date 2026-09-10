import yaml

from app.router_credentials_store import RouterCredentialsStore
from app.secrets_crypto import SecretsCipher


def test_get_returns_empty_when_no_file(tmp_path):
    store = RouterCredentialsStore(tmp_path / "router.yaml")
    creds = store.get()
    assert creds.username is None
    assert creds.password is None
    assert creds.use_https is False


def test_use_https_defaults_false_and_persists(tmp_path):
    store = RouterCredentialsStore(tmp_path / "router.yaml")
    updated = store.update({"use_https": True})
    assert updated.use_https is True
    assert store.get().use_https is True


def test_update_persists_and_ignores_none_values(tmp_path):
    store = RouterCredentialsStore(tmp_path / "router.yaml")
    updated = store.update({"username": "admin", "password": "hunter2"})
    assert updated.username == "admin"
    assert updated.password == "hunter2"

    updated2 = store.update({"username": None})
    assert updated2.username == "admin"
    assert updated2.password == "hunter2"

    reloaded = RouterCredentialsStore(tmp_path / "router.yaml").get()
    assert reloaded.username == "admin"
    assert reloaded.password == "hunter2"


def test_password_is_encrypted_at_rest(tmp_path):
    path = tmp_path / "router.yaml"
    cipher = SecretsCipher("a-secret-key")
    store = RouterCredentialsStore(path, cipher)
    store.update({"username": "admin", "password": "hunter2"})

    on_disk = yaml.safe_load(path.read_text())
    assert on_disk["password"] != "hunter2"
    assert cipher.decrypt(on_disk["password"]) == "hunter2"

    assert store.get().password == "hunter2"


def test_password_roundtrips_across_store_instances(tmp_path):
    path = tmp_path / "router.yaml"
    cipher = SecretsCipher("a-secret-key")
    RouterCredentialsStore(path, cipher).update({"username": "admin", "password": "hunter2"})
    reopened = RouterCredentialsStore(path, cipher)
    assert reopened.get().password == "hunter2"


def test_without_a_cipher_password_stays_plaintext(tmp_path):
    path = tmp_path / "router.yaml"
    RouterCredentialsStore(path).update({"username": "admin", "password": "hunter2"})
    on_disk = yaml.safe_load(path.read_text())
    assert on_disk["password"] == "hunter2"


def test_preexisting_plaintext_password_still_works_once_a_cipher_is_added(tmp_path):
    path = tmp_path / "router.yaml"
    RouterCredentialsStore(path).update({"username": "admin", "password": "hunter2"})

    upgraded = RouterCredentialsStore(path, SecretsCipher("a-secret-key"))
    assert upgraded.get().password == "hunter2"
