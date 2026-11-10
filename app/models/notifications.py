"""Notification delivery settings (webhook + email)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

# Alert delivery config: a webhook (any URL that accepts a JSON POST - IFTTT,
# Home Assistant, a Discord/Slack incoming webhook, ntfy, ...) and/or email
# (plain SMTP), fired on motion detection, a camera going offline/back
# online, and disk space running low. All optional and off by default.
class NotificationSettingsBase(BaseModel):
    webhook_enabled: bool = False
    webhook_url: Optional[str] = Field(default=None, max_length=500)
    email_enabled: bool = False
    smtp_host: Optional[str] = Field(default=None, max_length=255)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: Optional[str] = Field(default=None, max_length=255)
    smtp_password: Optional[str] = Field(default=None, max_length=255)
    smtp_use_tls: bool = True
    smtp_from: Optional[str] = Field(default=None, max_length=255)
    smtp_to: Optional[str] = Field(default=None, max_length=500)  # comma-separated recipients
    notify_on_motion: bool = True
    notify_on_camera_offline: bool = True
    notify_on_disk_low: bool = True
    notify_on_backup_failed: bool = True


class NotificationSettings(NotificationSettingsBase):
    pass


class NotificationSettingsUpdate(BaseModel):
    webhook_enabled: Optional[bool] = None
    webhook_url: Optional[str] = Field(default=None, max_length=500)
    email_enabled: Optional[bool] = None
    smtp_host: Optional[str] = Field(default=None, max_length=255)
    smtp_port: Optional[int] = Field(default=None, ge=1, le=65535)
    smtp_username: Optional[str] = Field(default=None, max_length=255)
    smtp_password: Optional[str] = Field(default=None, max_length=255)
    smtp_use_tls: Optional[bool] = None
    smtp_from: Optional[str] = Field(default=None, max_length=255)
    smtp_to: Optional[str] = Field(default=None, max_length=500)
    notify_on_motion: Optional[bool] = None
    notify_on_camera_offline: Optional[bool] = None
    notify_on_disk_low: Optional[bool] = None
    notify_on_backup_failed: Optional[bool] = None

