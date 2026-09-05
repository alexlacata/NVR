"""Admin-only read access to the recording view/download audit log - see
app.audit_log. Admin-only (not settings_manage) since it surveils what
*other* users did, unlike server config."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.audit_log import AuditLog
from app.deps import get_audit_log, require_admin

router = APIRouter(prefix="/api/audit", tags=["audit"], dependencies=[Depends(require_admin)])


@router.get("")
def list_audit_entries(
    limit: int = Query(default=200, ge=1, le=1000),
    audit_log: AuditLog = Depends(get_audit_log),
):
    return audit_log.recent(limit=limit)
