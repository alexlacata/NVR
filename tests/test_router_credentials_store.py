import pytest
import yaml

from app.models import RouterCredentialsUpdate
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


def test_ssh_username_and_port_default_none_and_persist(tmp_path):
    store = RouterCredentialsStore(tmp_path / "router.yaml")
    creds = store.get()
    assert creds.ssh_username is None
    assert creds.ssh_port is None
    updated = store.update({"ssh_username": "root", "ssh_port": 2222})
    assert updated.ssh_username == "root"
    assert updated.ssh_port == 2222
    assert store.get().ssh_username == "root"
    assert store.get().ssh_port == 2222


def test_update_persists_a_partial_patch_without_touching_other_fields(tmp_path):
    store = RouterCredentialsStore(tmp_path / "router.yaml")
    updated = store.update({"username": "admin", "password": "hunter2"})
    assert updated.username == "admin"
    assert updated.password == "hunter2"

    # A key simply absent from the patch (not sent by the caller) must
    # leave the existing value alone.
    updated2 = store.update({"use_https": True})
    assert updated2.username == "admin"
    assert updated2.password == "hunter2"
    assert updated2.use_https is True

    reloaded = RouterCredentialsStore(tmp_path / "router.yaml").get()
    assert reloaded.username == "admin"
    assert reloaded.password == "hunter2"


def test_update_with_explicit_none_clears_the_field(tmp_path):
    store = RouterCredentialsStore(tmp_path / "router.yaml")
    store.update({"username": "admin", "password": "hunter2"})

    cleared = store.update({"username": None})
    assert cleared.username is None
    assert cleared.password == "hunter2"
    assert store.get().username is None


def test_ip_override_defaults_none_and_persists(tmp_path):
    store = RouterCredentialsStore(tmp_path / "router.yaml")
    assert store.get().ip_override is None
    updated = store.update({"ip_override": "192.168.1.254"})
    assert updated.ip_override == "192.168.1.254"
    assert store.get().ip_override == "192.168.1.254"

    cleared = store.update({"ip_override": None})
    assert cleared.ip_override is None


def test_ip_override_rejects_non_ipv4_values():
    with pytest.raises(ValueError):
        RouterCredentialsUpdate(ip_override="not-an-ip")
    with pytest.raises(ValueError):
        RouterCredentialsUpdate(ip_override="router.local")


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
