import pytest

from app.models import UserCreate, UserRole, UserUpdate
from app.user_store import DuplicateUsername, LastAdminError, UserNotFound, UserStore, pwd_context


@pytest.fixture()
def store(tmp_path):
    return UserStore(tmp_path / "users.yaml")


def test_create_and_get(store):
    user = store.create(UserCreate(username="alice", password="s3cretpass", role=UserRole.admin))
    assert user.username == "alice"
    assert user.role == UserRole.admin
    assert pwd_context.verify("s3cretpass", user.password_hash)
    fetched = store.get("alice")
    assert fetched.username == "alice"


def test_get_is_case_insensitive(store):
    store.create(UserCreate(username="Alice", password="s3cretpass"))
    assert store.get("alice").username == "Alice"
    assert store.get("ALICE").username == "Alice"


def test_duplicate_username_rejected(store):
    store.create(UserCreate(username="alice", password="s3cretpass"))
    with pytest.raises(DuplicateUsername):
        store.create(UserCreate(username="alice", password="other1234"))
    with pytest.raises(DuplicateUsername):
        store.create(UserCreate(username="ALICE", password="other1234"))


def test_get_missing_raises(store):
    with pytest.raises(UserNotFound):
        store.get("nope")


def test_update_password(store):
    store.create(UserCreate(username="alice", password="s3cretpass"))
    updated = store.update("alice", UserUpdate(password="newpassword1"))
    assert pwd_context.verify("newpassword1", updated.password_hash)
    assert not pwd_context.verify("s3cretpass", updated.password_hash)


def test_update_role(store):
    store.create(UserCreate(username="alice", password="s3cretpass", role=UserRole.viewer))
    updated = store.update("alice", UserUpdate(role=UserRole.admin))
    assert updated.role == UserRole.admin


def test_delete(store):
    store.create(UserCreate(username="alice", password="s3cretpass"))
    store.delete("alice")
    with pytest.raises(UserNotFound):
        store.get("alice")


def test_cannot_delete_last_admin(store):
    store.create(UserCreate(username="admin", password="s3cretpass", role=UserRole.admin))
    with pytest.raises(LastAdminError):
        store.delete("admin")


def test_can_delete_admin_when_another_remains(store):
    store.create(UserCreate(username="admin1", password="s3cretpass", role=UserRole.admin))
    store.create(UserCreate(username="admin2", password="s3cretpass", role=UserRole.admin))
    store.delete("admin1")  # should not raise
    assert store.count_admins() == 1


def test_cannot_demote_last_admin(store):
    store.create(UserCreate(username="admin", password="s3cretpass", role=UserRole.admin))
    with pytest.raises(LastAdminError):
        store.update("admin", UserUpdate(role=UserRole.viewer))


def test_can_demote_admin_when_another_remains(store):
    store.create(UserCreate(username="admin1", password="s3cretpass", role=UserRole.admin))
    store.create(UserCreate(username="admin2", password="s3cretpass", role=UserRole.admin))
    updated = store.update("admin1", UserUpdate(role=UserRole.viewer))
    assert updated.role == UserRole.viewer
    assert store.count_admins() == 1


def test_is_empty(store):
    assert store.is_empty() is True
    store.create(UserCreate(username="alice", password="s3cretpass"))
    assert store.is_empty() is False


def test_count_admins(store):
    assert store.count_admins() == 0
    store.create(UserCreate(username="alice", password="s3cretpass", role=UserRole.admin))
    store.create(UserCreate(username="bob", password="s3cretpass", role=UserRole.viewer))
    assert store.count_admins() == 1
