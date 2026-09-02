import pytest

from app.config import Settings


def test_ensure_dirs_creates_data_dir_by_default(tmp_path):
    data_dir = tmp_path / "not-yet-mounted"
    settings = Settings(data_dir=data_dir, secret_key="x")
    settings.ensure_dirs()
    assert data_dir.is_dir()


def test_require_existing_data_dir_refuses_to_create_it(tmp_path):
    data_dir = tmp_path / "network-share-not-mounted"
    settings = Settings(data_dir=data_dir, require_existing_data_dir=True, secret_key="x")
    with pytest.raises(RuntimeError):
        settings.ensure_dirs()
    assert not data_dir.exists()


def test_require_existing_data_dir_ok_once_mounted(tmp_path):
    data_dir = tmp_path / "network-share"
    data_dir.mkdir()
    settings = Settings(data_dir=data_dir, require_existing_data_dir=True, secret_key="x")
    settings.ensure_dirs()  # should not raise
    assert (data_dir / "config").is_dir()
