"""Sends alerts (webhook + email) for motion detection, a camera going
offline/back online, and disk space running low. Delivery is best-effort:
failures are logged, never raised, so a broken webhook/SMTP config can
never take down the recording pipeline that triggered the alert."""
from __future__ import annotations

import asyncio
import logging
import smtplib
import time
from email.message import EmailMessage

import httpx

from app.models import NotificationSettings
from app.notification_settings_store import NotificationSettingsStore

logger = logging.getLogger("nvr.notifier")


class Notifier:
    def __init__(self, settings_store: NotificationSettingsStore):
        self._settings_store = settings_store
        self._last_sent: dict[str, float] = {}

    def _cooldown_ok(self, dedupe_key: str, cooldown_seconds: float) -> bool:
        now = time.monotonic()
        last = self._last_sent.get(dedupe_key, float("-inf"))
        if now - last < cooldown_seconds:
            return False
        self._last_sent[dedupe_key] = now
        return True

    async def notify(
        self, *, event: str, title: str, message: str, dedupe_key: str, cooldown_seconds: float = 0.0
    ) -> None:
        if cooldown_seconds and not self._cooldown_ok(dedupe_key, cooldown_seconds):
            return
        settings = self._settings_store.get()
        tasks = []
        if settings.webhook_enabled and settings.webhook_url:
            tasks.append(self._send_webhook(settings, event, title, message))
        if settings.email_enabled and settings.smtp_host and settings.smtp_to:
            tasks.append(asyncio.to_thread(self._send_email, settings, title, message))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_webhook(self, settings: NotificationSettings, event: str, title: str, message: str) -> None:
        payload = {"event": event, "title": title, "message": message, "at": time.time()}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(settings.webhook_url, json=payload)
        except Exception:
            logger.warning("notifier: webhook delivery failed", exc_info=True)

    def _send_email(self, settings: NotificationSettings, title: str, message: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = title
        msg["From"] = settings.smtp_from or settings.smtp_username or "nvr@localhost"
        msg["To"] = settings.smtp_to
        msg.set_content(message)
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls()
                if settings.smtp_username and settings.smtp_password:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(msg)
        except Exception:
            logger.warning("notifier: email delivery failed", exc_info=True)

    async def notify_motion(self, camera_id: str, camera_name: str) -> None:
        if not self._settings_store.get().notify_on_motion:
            return
        await self.notify(
            event="motion",
            title=f"Mouvement detecte - {camera_name}",
            message=f"Mouvement detecte sur la camera « {camera_name} ».",
            dedupe_key=f"motion:{camera_id}",
        )

    async def notify_camera_offline(self, camera_id: str, camera_name: str) -> None:
        if not self._settings_store.get().notify_on_camera_offline:
            return
        await self.notify(
            event="camera_offline",
            title=f"Camera hors ligne - {camera_name}",
            message=f"La camera « {camera_name} » semble hors ligne (erreur de flux persistante).",
            dedupe_key=f"camera_offline:{camera_id}",
        )

    async def notify_camera_online(self, camera_id: str, camera_name: str) -> None:
        if not self._settings_store.get().notify_on_camera_offline:
            return
        await self.notify(
            event="camera_online",
            title=f"Camera de nouveau en ligne - {camera_name}",
            message=f"La camera « {camera_name} » est de nouveau en ligne.",
            dedupe_key=f"camera_online:{camera_id}",
        )

    async def notify_disk_low(self, free_percent: float, cooldown_seconds: float) -> None:
        if not self._settings_store.get().notify_on_disk_low:
            return
        await self.notify(
            event="disk_low",
            title="Espace disque faible",
            message=f"Il ne reste que {free_percent:.1f}% d'espace libre sur le disque du NVR.",
            dedupe_key="disk_low",
            cooldown_seconds=cooldown_seconds,
        )

    async def send_test_notification(self) -> None:
        await self.notify(
            event="test",
            title="Test de notification NVR",
            message="Ceci est une notification de test envoyee depuis les parametres du NVR.",
            dedupe_key="test",
        )
