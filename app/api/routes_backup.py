"""Admin-only backup status + on-demand trigger - see app.backup.
backup_dir itself is env-var-only (a filesystem path, same category as
data_dir), so this is read-only status plus a manual "run now" button,
not a config editor."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.backup import BackupStatusTracker, sync_backup
from app.config import Settings
from app.deps import get_backup_status, get_settings, require_settings_manage

router = APIRouter(prefix="/api/backup", tags=["backup"], dependencies=[Depends(require_settings_manage)])


@router.get("/status")
def backup_status(
    settings: Settings = Depends(get_settings),
    status: BackupStatusTracker = Depends(get_backup_status),
):
    return {
        "enabled": bool(settings.backup_dir),
        "backup_dir": settings.backup_dir or None,
        "check_interval_seconds": settings.backup_check_interval_seconds,
        **status.snapshot(),
    }


@router.post("/run")
def run_backup_now(
    settings: Settings = Depends(get_settings),
    status: BackupStatusTracker = Depends(get_backup_status),
):
    report = sync_backup(settings)
    status.record(report)
    return {
        "copied_files": report.copied_files,
        "copied_bytes": report.copied_bytes,
        "failed_files": report.failed_files,
    }
