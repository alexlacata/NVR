"""Application configuration, sourced from environment variables (.env)."""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NVR_", extra="ignore")

    # Root directory where all persistent data lives. Point this at your
    # mounted hard drive, e.g. /mnt/nvr-disk.
    data_dir: Path = Path("data")

    # Auth
    admin_username: str = "admin"
    admin_password: str = "changeme"
    secret_key: str = ""  # auto-generated and persisted if left blank
    session_max_age_seconds: int = 60 * 60 * 24 * 30  # 30 days

    # Recording / retention
    segment_seconds: int = 600  # length of each recorded file (10 min)
    retention_days: int = 14  # delete recordings older than this
    min_free_disk_percent: float = 10.0  # start deleting oldest files below this
    retention_check_interval_seconds: int = 60

    # Thumbnails (used to scrub recordings on a timeline). Extracted from
    # finished recording segments, not a live camera connection, so they
    # cost no extra bandwidth to the camera.
    thumbnail_interval_seconds: int = 60  # default cadence, overridable per camera
    thumbnail_check_interval_seconds: int = 30

    # Live streaming (HLS)
    hls_segment_seconds: int = 2
    hls_list_size: int = 6

    # Networking
    host: str = "0.0.0.0"
    port: int = 8000

    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"

    @property
    def config_dir(self) -> Path:
        return self.data_dir / "config"

    @property
    def cameras_file(self) -> Path:
        return self.config_dir / "cameras.yaml"

    @property
    def recordings_dir(self) -> Path:
        return self.data_dir / "recordings"

    @property
    def hls_dir(self) -> Path:
        return self.data_dir / "hls"

    @property
    def thumbnails_dir(self) -> Path:
        return self.data_dir / "thumbnails"

    @property
    def secret_key_file(self) -> Path:
        return self.config_dir / "secret_key"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.config_dir, self.recordings_dir, self.hls_dir, self.thumbnails_dir):
            d.mkdir(parents=True, exist_ok=True)

    def resolve_secret_key(self) -> str:
        """Return the configured secret key, or a persisted auto-generated one."""
        if self.secret_key:
            return self.secret_key
        self.ensure_dirs()
        if self.secret_key_file.exists():
            return self.secret_key_file.read_text().strip()
        key = secrets.token_hex(32)
        self.secret_key_file.write_text(key)
        return key


@lru_cache
def get_settings() -> Settings:
    return Settings()
