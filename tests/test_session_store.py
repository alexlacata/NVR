from app.session_store import SessionStore


def test_record_and_exists(tmp_path):
    store = SessionStore(tmp_path / "sessions.yaml")
    store.record("jti1", "alice", "Mozilla/5.0", "10.0.0.1")
    assert store.exists("jti1") is True
    assert store.exists("nope") is False


def test_list_for_user_filters_and_sorts_newest_first(tmp_path):
    store = SessionStore(tmp_path / "sessions.yaml")
    store.record("jti1", "alice", "UA1", "1.1.1.1")
    store.record("jti2", "bob", "UA2", "2.2.2.2")
    store.record("jti3", "alice", "UA3", "3.3.3.3")

    entries = store.list_for_user("alice")
    assert [e["jti"] for e in entries] == ["jti3", "jti1"]  # newest first


def test_list_for_user_is_case_insensitive(tmp_path):
    store = SessionStore(tmp_path / "sessions.yaml")
    store.record("jti1", "Alice", "UA", "1.1.1.1")
    assert len(store.list_for_user("alice")) == 1
    assert len(store.list_for_user("ALICE")) == 1


def test_revoke_removes_session(tmp_path):
    store = SessionStore(tmp_path / "sessions.yaml")
    store.record("jti1", "alice", "UA", "1.1.1.1")
    assert store.revoke("jti1") is True
    assert store.exists("jti1") is False
    assert store.revoke("jti1") is False  # already gone


def test_revoke_all_for_user_except_one(tmp_path):
    store = SessionStore(tmp_path / "sessions.yaml")
    store.record("jti1", "alice", "UA", "1.1.1.1")
    store.record("jti2", "alice", "UA", "1.1.1.1")
    store.record("jti3", "bob", "UA", "1.1.1.1")

    removed = store.revoke_all_for_user("alice", except_jti="jti2")
    assert removed == 1
    assert store.exists("jti1") is False
    assert store.exists("jti2") is True
    assert store.exists("jti3") is True  # a different user, untouched


def test_persists_across_instances(tmp_path):
    path = tmp_path / "sessions.yaml"
    SessionStore(path).record("jti1", "alice", "UA", "1.1.1.1")
    reloaded = SessionStore(path)
    assert reloaded.exists("jti1") is True


def test_in_memory_store_without_path(tmp_path):
    store = SessionStore()  # no path - ephemeral
    store.record("jti1", "alice", "UA", "1.1.1.1")
    assert store.exists("jti1") is True
    # a fresh in-memory instance never sees another instance's sessions
    assert SessionStore().exists("jti1") is False


def test_prune_expired_removes_old_sessions(tmp_path, monkeypatch):
    import app.session_store as session_store_module
    from datetime import datetime, timedelta, timezone

    store = SessionStore(tmp_path / "sessions.yaml")
    old_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

    # record it normally then backdate created_at directly on disk
    store.record("jti1", "alice", "UA", "1.1.1.1")
    sessions = store._read()
    sessions["jti1"]["created_at"] = old_time
    store._write(sessions)

    store.prune_expired(max_age_seconds=3600)
    assert store.exists("jti1") is False


def test_list_for_user_with_max_age_prunes_expired(tmp_path):
    from datetime import datetime, timedelta, timezone

    store = SessionStore(tmp_path / "sessions.yaml")
    store.record("jti1", "alice", "UA", "1.1.1.1")
    sessions = store._read()
    sessions["jti1"]["created_at"] = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    store._write(sessions)
    store.record("jti2", "alice", "UA", "1.1.1.1")

    entries = store.list_for_user("alice", max_age_seconds=3600)
    assert [e["jti"] for e in entries] == ["jti2"]
    assert store.exists("jti1") is False  # pruned from disk, not just filtered from the result
