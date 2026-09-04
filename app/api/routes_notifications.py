"""Admin-only alert delivery config (webhook/email) - see app.notifier and
app.notification_settings_store. Kept entirely behind settings_manage
(unlike, say, the cameras list) since it can hold an SMTP password."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_notification_settings_store, get_notifier, require_settings_manage
from app.models import NotificationSettings, NotificationSettingsUpdate
from app.notification_settings_store import NotificationSettingsStore
from app.notifier import Notifier

router = APIRouter(
    prefix="/api/notifications", tags=["notifications"], dependencies=[Depends(require_settings_manage)]
)


@router.get("/settings", response_model=NotificationSettings)
def get_notification_settings(store: NotificationSettingsStore = Depends(get_notification_settings_store)):
    return store.get()


@router.patch("/settings", response_model=NotificationSettings)
def update_notification_settings(
    payload: NotificationSettingsUpdate,
    store: NotificationSettingsStore = Depends(get_notification_settings_store),
):
    return store.update(payload.model_dump(exclude_unset=True))


@router.post("/test")
async def send_test_notification(notifier: Notifier = Depends(get_notifier)):
    await notifier.send_test_notification()
    return {"ok": True}
