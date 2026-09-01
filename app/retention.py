"""Keeps recordings (and their thumbnails) from filling up the disk:
deletes files older than `retention_days`, and if free space still falls
below `min_free_disk_percent`, deletes the oldest remaining files (across
all cameras) until it doesn't.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings

logger = logging.getLogger("nvr.retention")


@dataclass
class RetentionReport:
    deleted_files: int = 0
    freed_bytes: int = 0
    reason: str = ""


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
    if free_percent >= settings.min_free_disk_percent:
        return report

    files = sorted(_managed_files(settings), key=lambda p: _safe_mtime(p))
    for f in files:
        usage = shutil.disk_usage(settings.data_dir)
        free_percent = 100.0 * usage.free / usage.total if usage.total else 100.0
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


async def retention_loop(settings: Settings, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(enforce_retention, settings)
        except Exception:  # pragma: no cover - defensive
            logger.exception("retention: unexpected error")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.retention_check_interval_seconds)
        except asyncio.TimeoutError:
            pass
