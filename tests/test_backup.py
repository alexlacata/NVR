from app.backup import BackupStatusTracker, sync_backup
from app.config import Settings


def _make_recording(base, camera_id, filename, content=b"data"):
    path = base / camera_id / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_backup_disabled_when_backup_dir_blank(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", backup_dir="")
    settings.ensure_dirs()
    _make_recording(settings.recordings_dir, "cam1", "2024-01-01_00-00-00.mp4")
    report = sync_backup(settings)
    assert report.copied_files == 0
    assert not (tmp_path / "backup").exists()


def test_backup_copies_new_recordings(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", backup_dir=str(tmp_path / "backup"))
    settings.ensure_dirs()
    content = b"recording bytes" * 100
    _make_recording(settings.recordings_dir, "cam1", "2024-01-01_00-00-00.mp4", content)

    report = sync_backup(settings)

    assert report.copied_files == 1
    assert report.copied_bytes == len(content)
    dest = tmp_path / "backup" / "cam1" / "2024-01-01_00-00-00.mp4"
    assert dest.is_file()
    assert dest.read_bytes() == content
    assert not dest.with_suffix(dest.suffix + ".partial").exists()


def test_backup_skips_already_copied_same_size_files(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", backup_dir=str(tmp_path / "backup"))
    settings.ensure_dirs()
    _make_recording(settings.recordings_dir, "cam1", "2024-01-01_00-00-00.mp4", b"x" * 500)

    sync_backup(settings)
    report2 = sync_backup(settings)

    assert report2.copied_files == 0


def test_backup_recopies_when_destination_size_differs(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", backup_dir=str(tmp_path / "backup"))
    settings.ensure_dirs()
    src = _make_recording(settings.recordings_dir, "cam1", "2024-01-01_00-00-00.mp4", b"x" * 500)
    sync_backup(settings)

    # simulate a truncated previous copy
    dest = tmp_path / "backup" / "cam1" / "2024-01-01_00-00-00.mp4"
    dest.write_bytes(b"x" * 100)

    report = sync_backup(settings)
    assert report.copied_files == 1
    assert dest.read_bytes() == src.read_bytes()


def test_backup_does_not_touch_hls_or_thumbnails(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", backup_dir=str(tmp_path / "backup"))
    settings.ensure_dirs()
    (settings.hls_dir / "cam1").mkdir(parents=True)
    (settings.hls_dir / "cam1" / "seg_001.ts").write_bytes(b"x")
    (settings.thumbnails_dir / "cam1").mkdir(parents=True)
    (settings.thumbnails_dir / "cam1" / "thumb.jpg").write_bytes(b"x")

    report = sync_backup(settings)
    assert report.copied_files == 0
    assert not (tmp_path / "backup").exists() or not any((tmp_path / "backup").rglob("*"))


def test_backup_continues_after_one_file_fails(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path / "data", backup_dir=str(tmp_path / "backup"))
    settings.ensure_dirs()
    _make_recording(settings.recordings_dir, "cam1", "2024-01-01_00-00-00.mp4", b"a")
    _make_recording(settings.recordings_dir, "cam1", "2024-01-01_01-00-00.mp4", b"b")

    import shutil
    real_copy2 = shutil.copy2
    calls = {"n": 0}

    def flaky_copy2(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated failure")
        return real_copy2(src, dst)

    monkeypatch.setattr("app.backup.shutil.copy2", flaky_copy2)
    report = sync_backup(settings)
    assert report.failed_files == 1
    assert report.copied_files == 1


def test_backup_status_tracker_snapshot_before_and_after_record():
    tracker = BackupStatusTracker()
    empty = tracker.snapshot()
    assert empty["last_run_at"] is None
    assert empty["last_copied_files"] is None

    from app.backup import BackupReport
    tracker.record(BackupReport(copied_files=3, copied_bytes=999, failed_files=1))
    snap = tracker.snapshot()
    assert snap["last_run_at"] is not None
    assert snap["last_copied_files"] == 3
    assert snap["last_copied_bytes"] == 999
    assert snap["last_failed_files"] == 1
