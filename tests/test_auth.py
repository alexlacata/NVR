from app.auth import AuthService, bootstrap_admin
from app.config import Settings
from app.models import UserRole
from app.user_store import UserStore


def _settings(tmp_path, **overrides):
    defaults = dict(
        data_dir=tmp_path,
        admin_username="admin",
        admin_password="s3cret-pass",
        secret_key="test-secret-key",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def test_bootstrap_admin_creates_initial_account(tmp_path):
    settings = _settings(tmp_path)
    users = UserStore(tmp_path / "users.yaml")
    bootstrap_admin(settings, users)
    user = users.get("admin")
    assert user.role == UserRole.admin


def test_bootstrap_admin_is_noop_if_users_exist(tmp_path):
    settings = _settings(tmp_path, admin_username="admin", admin_password="s3cret-pass")
    users = UserStore(tmp_path / "users.yaml")
    bootstrap_admin(settings, users)

    # changing the env-var creds and re-running bootstrap must not create
    # a second account or touch the existing one
    settings2 = _settings(tmp_path, admin_username="someoneelse", admin_password="whatever123")
    bootstrap_admin(settings2, users)

    assert len(users.list()) == 1
    assert users.try_get("someoneelse") is None
    assert users.try_get("admin") is not None


def test_verify_credentials_success(tmp_path):
    settings = _settings(tmp_path)
    users = UserStore(tmp_path / "users.yaml")
    bootstrap_admin(settings, users)
    auth = AuthService(settings, users)

    user = auth.verify_credentials("admin", "s3cret-pass")
    assert user is not None
    assert user.username == "admin"


def test_verify_credentials_wrong_password(tmp_path):
    settings = _settings(tmp_path)
    users = UserStore(tmp_path / "users.yaml")
    bootstrap_admin(settings, users)
    auth = AuthService(settings, users)
    assert auth.verify_credentials("admin", "wrong") is None


def test_verify_credentials_unknown_user(tmp_path):
    settings = _settings(tmp_path)
    users = UserStore(tmp_path / "users.yaml")
    bootstrap_admin(settings, users)
    auth = AuthService(settings, users)
    assert auth.verify_credentials("nobody", "whatever") is None


def test_token_roundtrip(tmp_path):
    settings = _settings(tmp_path)
    users = UserStore(tmp_path / "users.yaml")
    bootstrap_admin(settings, users)
    auth = AuthService(settings, users)

    token = auth.create_token("admin")
    user = auth.verify_token(token)
    assert user is not None
    assert user.username == "admin"


def test_verify_token_invalid_signature(tmp_path):
    settings = _settings(tmp_path)
    users = UserStore(tmp_path / "users.yaml")
    bootstrap_admin(settings, users)
    auth = AuthService(settings, users)
    assert auth.verify_token("not-a-real-token") is None


def test_verify_token_deleted_user_no_longer_valid(tmp_path):
    settings = _settings(tmp_path)
    users = UserStore(tmp_path / "users.yaml")
    bootstrap_admin(settings, users)
    from app.models import UserCreate
    users.create(UserCreate(username="temp", password="temppass123", role=UserRole.admin))
    auth = AuthService(settings, users)

    token = auth.create_token("temp")
    assert auth.verify_token(token) is not None
    users.delete("temp")
    assert auth.verify_token(token) is None
