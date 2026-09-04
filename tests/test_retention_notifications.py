import asyncio

from app.config import Settings
from app.retention import retention_loop


class FakeNotifier:
    def __init__(self):
        self.disk_low_calls = []

    async def notify_disk_low(self, free_percent, cooldown_seconds):
        self.disk_low_calls.append((free_percent, cooldown_seconds))


async def test_retention_loop_notifies_when_disk_stays_low(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        retention_days=30,
        min_free_disk_percent=100,  # unreachable -> always "low" after cleanup
        retention_check_interval_seconds=9999,
        disk_low_notify_cooldown_seconds=9999,
    )
    settings.ensure_dirs()
    notifier = FakeNotifier()
    stop_event = asyncio.Event()

    async def _stop_after_one_pass():
        await asyncio.sleep(0.05)
        stop_event.set()

    asyncio.create_task(_stop_after_one_pass())
    await retention_loop(settings, stop_event, notifier)

    assert len(notifier.disk_low_calls) == 1
    free_percent, cooldown = notifier.disk_low_calls[0]
    assert free_percent < 100
    assert cooldown == 9999


async def test_retention_loop_does_not_notify_when_disk_healthy(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        retention_days=30,
        min_free_disk_percent=0,  # always healthy
        retention_check_interval_seconds=9999,
    )
    settings.ensure_dirs()
    notifier = FakeNotifier()
    stop_event = asyncio.Event()

    async def _stop_after_one_pass():
        await asyncio.sleep(0.05)
        stop_event.set()

    asyncio.create_task(_stop_after_one_pass())
    await retention_loop(settings, stop_event, notifier)

    assert notifier.disk_low_calls == []
