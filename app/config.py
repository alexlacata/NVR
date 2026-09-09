"""Application configuration, sourced from environment variables (.env)."""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NVR_", extra="ignore")

    # Root directory where all persistent data lives. Point this at your
    # mounted hard drive, e.g. /mnt/nvr-disk - whether that's a drive
    # plugged directly into this machine, or a network share (SMB/NFS)
    # mounted at the OS level, e.g. one exposed by a Peplink router's USB
    # port. Either way this is just treated as a plain directory.
    data_dir: Path = Path("data")

    # When data_dir is meant to be a mount point (typically a network
    # share), a boot-order race can leave it un-mounted when the app
    # starts: mkdir() below would then silently create an empty local
    # directory instead of failing, the app would happily start recording
    # onto local disk, and once the real share mounts later it hides those
    # local files underneath it (they're still there, just inaccessible
    # until the share is unmounted again) - a classic, hard-to-notice way
    # to "lose" recordings. Set this to true to instead refuse to start
    # until data_dir already exists (i.e. until the share is mounted).
    require_existing_data_dir: bool = False

    # Auth. admin_username/admin_password only seed the initial admin
    # account the first time the server starts (when no users exist yet) -
    # once created, manage accounts from the web UI; changing these env
    # vars afterwards has no further effect.
    admin_username: str = "admin"
    admin_password: str = "changeme"
    secret_key: str = ""  # auto-generated and persisted if left blank
    session_max_age_seconds: int = 60 * 60 * 24 * 30  # 30 days

    # Login anti-bruteforce: after login_max_attempts failed logins for the
    # same username within login_attempt_window_seconds, that username is
    # locked out for login_lockout_seconds.
    login_max_attempts: int = 5
    login_attempt_window_seconds: int = 300
    login_lockout_seconds: int = 300

    # General API rate limiting: beyond the login-specific anti-bruteforce
    # above, caps how many requests any single identity (the authenticated
    # username, or the client IP before login) can make to the API within
    # rate_limit_window_seconds, so no one endpoint can be hammered.
    rate_limit_max_requests: int = 120
    rate_limit_window_seconds: int = 60

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

    # Motion detection sampling cadence (seconds between frame grabs per
    # camera, for cameras with motion_enabled). Independent of retention/
    # thumbnail cadence since it needs to be more frequent to feel responsive.
    motion_check_interval_seconds: int = 5
    # Minimum gap between two recorded motion *events* for the same camera,
    # so continuous motion doesn't spam an event every single check.
    motion_event_cooldown_seconds: int = 30

    # Backup: mirrors recordings (not HLS/thumbnails - those are ephemeral/
    # derived) to a second location, e.g. a NAS mount or a second disk -
    # blank (the default) disables it entirely. A plain directory, exactly
    # like data_dir: whether that's a drive plugged in locally or a network
    # share mounted at the OS level is not this app's concern.
    backup_dir: str = ""
    backup_check_interval_seconds: int = 300

    # Notifications (webhook/email) health checks
    camera_health_check_interval_seconds: int = 15
    # A camera has to be continuously in "error" state for this long before
    # an offline alert fires - a single ffmpeg reconnect blip (a few
    # seconds) is normal and shouldn't page anyone.
    camera_offline_after_seconds: int = 120
    disk_low_notify_cooldown_seconds: int = 3600

    # Networking
    host: str = "0.0.0.0"
    port: int = 8000

    # Native HTTPS (optional): when both are set, `python -m app.main`
    # serves TLS directly instead of plain HTTP - handy for a standalone
    # box with no reverse proxy in front of it. Leave blank (the default)
    # to serve plain HTTP, e.g. behind Tailscale/WireGuard or a reverse
    # proxy that terminates TLS itself (Caddy/Nginx + Let's Encrypt) - see
    # scripts/generate-self-signed-cert.sh for a quick self-signed pair.
    ssl_certfile: str = ""
    ssl_keyfile: str = ""

    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"

    @property
    def config_dir(self) -> Path:
        return self.data_dir / "config"

    @property
    def cameras_file(self) -> Path:
        return self.config_dir / "cameras.yaml"

    @property
    def users_file(self) -> Path:
        return self.config_dir / "users.yaml"

    @property
    def runtime_settings_file(self) -> Path:
        return self.config_dir / "settings.yaml"

    @property
    def systems_file(self) -> Path:
        return self.config_dir / "systems.yaml"

    @property
    def notification_settings_file(self) -> Path:
        return self.config_dir / "notifications.yaml"

    @property
    def audit_log_file(self) -> Path:
        return self.config_dir / "audit.jsonl"

    @property
    def sessions_file(self) -> Path:
        return self.config_dir / "sessions.yaml"

    @property
    def router_credentials_file(self) -> Path:
        return self.config_dir / "router_credentials.yaml"

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
    def motion_dir(self) -> Path:
        return self.data_dir / "motion"

    @property
    def secret_key_file(self) -> Path:
        return self.config_dir / "secret_key"

    def ensure_dirs(self) -> None:
        if self.require_existing_data_dir and not self.data_dir.is_dir():
            raise RuntimeError(
                f"NVR_REQUIRE_EXISTING_DATA_DIR est actif et {self.data_dir} n'existe pas encore. "
                "Si data_dir est un partage reseau (SMB/NFS, ex. un disque expose par un routeur "
                "Peplink), c'est probablement qu'il n'est pas encore monte - verifiez le montage "
                "(systemd .mount/automount ou /etc/fstab) avant de relancer le service."
            )
        for d in (self.data_dir, self.config_dir, self.recordings_dir, self.hls_dir, self.thumbnails_dir, self.motion_dir):
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
