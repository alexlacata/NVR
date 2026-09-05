"""Mirrors recordings (not HLS/thumbnails - those are ephemeral/derived,
not worth duplicating) to a second location: a mounted NAS, a second
disk, anything reachable as a plain directory. Disabled entirely when
Settings.backup_dir is blank.

Deliberately a size-based "already backed up" check rather than a content
hash - cheap enough to run every cycle over potentially thousands of
files, and a segment file is written once by ffmpeg and never modified
afterwards, so a same-size destination copy is already a reliable signal
short of extremely unlucky corruption (which retention/disk failures
would surface elsewhere anyway)."""
from __future__ import annotations

import asyncio
import logging
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import Settings
from app.notifier import Notifier

logger = logging.getLogger("nvr.backup")


@dataclass
class BackupReport:
    copied_files: int = 0
    copied_bytes: int = 0
    failed_files: int = 0


class BackupStatusTracker:
    """The last backup_loop run's outcome, for the admin-facing status
    view - not persisted, a fresh server start just has no "last run" yet."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_run_at: Optional[str] = None
        self._last_report: Optional[BackupReport] = None

    def record(self, report: BackupReport) -> None:
        with self._lock:
            self._last_run_at = datetime.now(timezone.utc).isoformat()
            self._last_report = report

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "last_run_at": self._last_run_at,
                "last_copied_files": self._last_report.copied_files if self._last_report else None,
                "last_copied_bytes": self._last_report.copied_bytes if self._last_report else None,
                "last_failed_files": self._last_report.failed_files if self._last_report else None,
            }


def _iter_recording_files(recordings_dir: Path):
    if not recordings_dir.exists():
        return
    for camera_dir in recordings_dir.iterdir():
        if not camera_dir.is_dir():
            continue
        for f in camera_dir.glob("*.mp4"):
            yield camera_dir.name, f


def _already_backed_up(dest: Path, src_size: int) -> bool:
    try:
        return dest.is_file() and dest.stat().st_size == src_size
    except OSError:
        return False


def sync_backup(settings: Settings) -> BackupReport:
    report = BackupReport()
    if not settings.backup_dir:
        return report
    backup_root = Path(settings.backup_dir)
    try:
        backup_root.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.warning("backup: destination %s is not reachable/writable", backup_root)
        report.failed_files += 1
        return report

    for camera_id, src in _iter_recording_files(settings.recordings_dir):
        try:
            src_size = src.stat().st_size
        except OSError:
            continue
        dest_dir = backup_root / camera_id
        dest = dest_dir / src.name
        if _already_backed_up(dest, src_size):
            continue
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            tmp_dest = dest.with_suffix(dest.suffix + ".partial")
            shutil.copy2(src, tmp_dest)
            tmp_dest.replace(dest)
            report.copied_files += 1
            report.copied_bytes += src_size
        except OSError:
            logger.warning("backup: failed to copy %s to %s", src, dest, exc_info=True)
            report.failed_files += 1

    if report.copied_files or report.failed_files:
        logger.info(
            "backup: copied %d file(s) (%.1f MB), %d failure(s)",
            report.copied_files, report.copied_bytes / 1e6, report.failed_files,
        )
    return report


async def backup_loop(
    settings: Settings,
    stop_event: asyncio.Event,
    notifier: Optional[Notifier] = None,
    status: Optional[BackupStatusTracker] = None,
) -> None:
    while not stop_event.is_set():
        if settings.backup_dir:
            try:
                report = await asyncio.to_thread(sync_backup, settings)
                if status is not None:
                    status.record(report)
                if notifier is not None and report.failed_files:
                    await notifier.notify_backup_failed(settings.backup_dir, report.failed_files)
            except Exception:  # pragma: no cover - defensive
                logger.exception("backup: unexpected error")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.backup_check_interval_seconds)
        except asyncio.TimeoutError:
            pass
