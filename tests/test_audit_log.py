from app.audit_log import AuditLog


def test_recent_is_empty_when_no_file(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    assert log.recent() == []


def test_record_and_recent_most_recent_first(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.record("alice", "view", "cam1", "a.mp4")
    log.record("bob", "download", "cam1", "b.mp4")
    entries = log.recent()
    assert len(entries) == 2
    assert entries[0]["username"] == "bob"
    assert entries[0]["action"] == "download"
    assert entries[1]["username"] == "alice"


def test_recent_respects_limit(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    for i in range(5):
        log.record("alice", "view", "cam1", f"{i}.mp4")
    entries = log.recent(limit=2)
    assert len(entries) == 2
    assert entries[0]["filename"] == "4.mp4"


def test_dedupe_seconds_suppresses_repeated_view_entries(monkeypatch, tmp_path):
    fake_now = [0.0]
    monkeypatch.setattr("app.audit_log.time.monotonic", lambda: fake_now[0])
    log = AuditLog(tmp_path / "audit.jsonl")

    log.record("alice", "view", "cam1", "a.mp4", dedupe_seconds=60)
    log.record("alice", "view", "cam1", "a.mp4", dedupe_seconds=60)
    assert len(log.recent()) == 1

    fake_now[0] += 61
    log.record("alice", "view", "cam1", "a.mp4", dedupe_seconds=60)
    assert len(log.recent()) == 2


def test_dedupe_is_scoped_per_key(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.record("alice", "view", "cam1", "a.mp4", dedupe_seconds=60)
    log.record("bob", "view", "cam1", "a.mp4", dedupe_seconds=60)  # different user
    log.record("alice", "view", "cam2", "a.mp4", dedupe_seconds=60)  # different camera
    log.record("alice", "download", "cam1", "a.mp4", dedupe_seconds=60)  # different action
    assert len(log.recent()) == 4


def test_download_without_dedupe_always_records(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.record("alice", "download", "cam1", "a.mp4")
    log.record("alice", "download", "cam1", "a.mp4")
    assert len(log.recent()) == 2
