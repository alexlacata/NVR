import os
import time
from unittest import mock

from app.config import Settings
from app.retention import enforce_retention


def _make_file(path, age_seconds=0, size=1024):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"0" * size)
    if age_seconds:
        t = time.time() - age_seconds
        os.utime(path, (t, t))


def test_deletes_files_older_than_retention(tmp_path):
    settings = Settings(data_dir=tmp_path, retention_days=1, min_free_disk_percent=0)
    settings.ensure_dirs()
    old_file = settings.recordings_dir / "cam1" / "2020-01-01_00-00-00.mp4"
    new_file = settings.recordings_dir / "cam1" / "2099-01-01_00-00-00.mp4"
    _make_file(old_file, age_seconds=2 * 86400)
    _make_file(new_file, age_seconds=0)

    report = enforce_retention(settings)

    assert not old_file.exists()
    assert new_file.exists()
    assert report.deleted_files == 1
    assert report.reason == "age"


def test_keeps_files_within_retention_when_disk_ok(tmp_path):
    settings = Settings(data_dir=tmp_path, retention_days=30, min_free_disk_percent=0)
    settings.ensure_dirs()
    f = settings.recordings_dir / "cam1" / "recent.mp4"
    _make_file(f, age_seconds=10)

    report = enforce_retention(settings)

    assert f.exists()
    assert report.deleted_files == 0


def test_deletes_oldest_first_when_disk_low(tmp_path):
    settings = Settings(data_dir=tmp_path, retention_days=365, min_free_disk_percent=99.999)
    settings.ensure_dirs()
    older = settings.recordings_dir / "cam1" / "older.mp4"
    newer = settings.recordings_dir / "cam1" / "newer.mp4"
    _make_file(older, age_seconds=1000)
    _make_file(newer, age_seconds=10)

    # Force disk usage to always report as "low free space" so the loop
    # keeps deleting until files run out, deterministically, regardless of
    # the sandbox's real free disk space.
    class FakeUsage:
        total = 100
        free = 1

    with mock.patch("app.retention.shutil.disk_usage", return_value=FakeUsage()):
        report = enforce_retention(settings)

    assert not older.exists()
    assert not newer.exists()
    assert report.deleted_files == 2
    assert report.reason == "disk_space"


def test_retention_days_zero_never_deletes_by_age(tmp_path):
    # "ecrasement permanent" mode: no age-based cutoff at all, however old
    # a file is - only the disk-space pass (exercised by the test above)
    # can delete anything.
    settings = Settings(data_dir=tmp_path, retention_days=0, min_free_disk_percent=0)
    settings.ensure_dirs()
    ancient_file = settings.recordings_dir / "cam1" / "2000-01-01_00-00-00.mp4"
    _make_file(ancient_file, age_seconds=20 * 365 * 86400)

    report = enforce_retention(settings)

    assert ancient_file.exists()
    assert report.deleted_files == 0


def test_retention_days_zero_still_honors_disk_space_eviction(tmp_path):
    settings = Settings(data_dir=tmp_path, retention_days=0, min_free_disk_percent=99.999)
    settings.ensure_dirs()
    f = settings.recordings_dir / "cam1" / "2000-01-01_00-00-00.mp4"
    _make_file(f, age_seconds=20 * 365 * 86400)

    class FakeUsage:
        total = 100
        free = 1

    with mock.patch("app.retention.shutil.disk_usage", return_value=FakeUsage()):
        report = enforce_retention(settings)

    assert not f.exists()
    assert report.deleted_files == 1
    assert report.reason == "disk_space"
