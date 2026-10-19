"""Keeps recordings (and their thumbnails) from filling up the disk:
deletes files older than `retention_days` (unless it's 0, meaning no age
limit - "ecrasement permanent" mode), and if free space still falls below
`min_free_disk_percent`, deletes the oldest remaining files (across all
cameras) until it doesn't.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.config import Settings
from app.notifier import Notifier

logger = logging.getLogger("nvr.retention")


@dataclass
class RetentionReport:
    deleted_files: int = 0
    freed_bytes: int = 0
    reason: str = ""
    free_percent: float = 100.0


def _iter_files(base_dir: Path, pattern: str):
    if not base_dir.exists():
        return
    for camera_dir in base_dir.iterdir():
        if not camera_dir.is_dir():
            continue
        for f in camera_dir.glob(pattern):
            yield f


def _managed_files(settings: Settings):
    yield from _iter_files(settings.recordings_dir, "*.mp4")
    yield from _iter_files(settings.thumbnails_dir, "*.jpg")
    yield from _iter_files(settings.thumbnails_dir, ".done-*")  # per-segment "processed" markers


def enforce_retention(settings: Settings) -> RetentionReport:
    report = RetentionReport()
    now = time.time()

    # retention_days == 0 is the "ecrasement permanent" mode: no age-based
    # cutoff at all, recordings only ever get deleted by the disk-space
    # pass below once free space runs low - a continuous-loop DVR.
    if settings.retention_days > 0:
        max_age = settings.retention_days * 86400
        for f in list(_managed_files(settings)):
            try:
                age = now - f.stat().st_mtime
            except OSError:
                continue
            if age > max_age:
                size = _safe_size(f)
                if _safe_unlink(f):
                    report.deleted_files += 1
                    report.freed_bytes += size
                    report.reason = "age"

    usage = shutil.disk_usage(settings.data_dir)
    free_percent = 100.0 * usage.free / usage.total if usage.total else 100.0
    report.free_percent = free_percent
    if free_percent >= settings.min_free_disk_percent:
        return report

    files = sorted(_managed_files(settings), key=lambda p: _safe_mtime(p))
    for f in files:
        usage = shutil.disk_usage(settings.data_dir)
        free_percent = 100.0 * usage.free / usage.total if usage.total else 100.0
        report.free_percent = free_percent
        if free_percent >= settings.min_free_disk_percent:
            break
        size = _safe_size(f)
        if _safe_unlink(f):
            report.deleted_files += 1
            report.freed_bytes += size
            report.reason = "disk_space"

    if report.deleted_files:
        logger.info(
            "retention: deleted %d file(s), freed %.1f MB (reason=%s)",
            report.deleted_files, report.freed_bytes / 1e6, report.reason,
        )
    return report


def _safe_unlink(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except OSError as exc:
        logger.warning("retention: could not delete %s: %s", path, exc)
        return False


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return time.time()


async def retention_loop(
    settings: Settings, stop_event: asyncio.Event, notifier: Optional[Notifier] = None
) -> None:
    while not stop_event.is_set():
        try:
            report = await asyncio.to_thread(enforce_retention, settings)
            if notifier is not None and report.free_percent < settings.min_free_disk_percent:
                # Cleanup ran and still couldn't bring free space back above
                # the threshold - genuinely critical, worth an alert (with
                # its own cooldown so a persistently full disk doesn't spam
                # one message per retention check).
                await notifier.notify_disk_low(report.free_percent, settings.disk_low_notify_cooldown_seconds)
        except Exception:  # pragma: no cover - defensive
            logger.exception("retention: unexpected error")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.retention_check_interval_seconds)
        except asyncio.TimeoutError:
            pass
