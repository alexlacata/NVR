import asyncio
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.models import SCHEDULE_CELLS, Camera, SourceType, schedule_allows_recording


def _base(**kwargs):
    defaults = dict(id="cam1", name="Cam 1", source_type=SourceType.rtsp, url="rtsp://x/1")
    defaults.update(kwargs)
    return defaults


def test_empty_schedule_always_allows_recording():
    cam = Camera(**_base())
    assert cam.record_schedule == []
    # Monday 03:00 and Sunday 23:00 - arbitrary times, both fine
    assert schedule_allows_recording(cam, datetime(2024, 1, 1, 3, 0)) is True
    assert schedule_allows_recording(cam, datetime(2024, 1, 7, 23, 0)) is True


def test_schedule_wrong_length_rejected():
    with pytest.raises(ValidationError):
        Camera(**_base(record_schedule=[True, False]))


def test_schedule_full_length_accepted_and_enforced():
    schedule = [False] * SCHEDULE_CELLS
    # Monday (weekday 0) hour 9 allowed
    schedule[0 * 24 + 9] = True
    cam = Camera(**_base(record_schedule=schedule))

    monday_9am = datetime(2024, 1, 1, 9, 30)  # 2024-01-01 is a Monday
    assert monday_9am.weekday() == 0
    assert schedule_allows_recording(cam, monday_9am) is True

    monday_10am = datetime(2024, 1, 1, 10, 0)
    assert schedule_allows_recording(cam, monday_10am) is False

    tuesday_9am = datetime(2024, 1, 2, 9, 30)
    assert schedule_allows_recording(cam, tuesday_9am) is False


def test_all_true_schedule_behaves_like_no_schedule():
    cam = Camera(**_base(record_schedule=[True] * SCHEDULE_CELLS))
    for hour in (0, 6, 12, 18, 23):
        assert schedule_allows_recording(cam, datetime(2024, 1, 3, hour, 0)) is True


class FakeCamera:
    def __init__(self, id="cam1", enabled=True, record=True, record_schedule=None):
        self.id = id
        self.enabled = enabled
        self.record = record
        self.record_schedule = record_schedule or []


class FakeLeg:
    def __init__(self):
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True
        self.stopped = False

    async def stop(self):
        self.stopped = True
        self.started = False


@pytest.mark.asyncio
async def test_sync_recording_schedule_starts_and_stops_record_leg():
    from app.ffmpeg_manager import StreamManager

    manager = StreamManager.__new__(StreamManager)  # bypass __init__, we only need _legs
    manager._legs = {}
    manager._configs = {}

    record_leg = FakeLeg()
    live_leg = FakeLeg()
    manager._legs["cam1"] = {"record": record_leg, "live": live_leg}

    schedule = [False] * SCHEDULE_CELLS
    monday_9am = datetime(2024, 1, 1, 9, 0)
    assert monday_9am.weekday() == 0
    schedule[0 * 24 + 9] = True
    camera = FakeCamera(record_schedule=schedule)

    manager.sync_recording_schedule([camera], now=monday_9am)
    assert record_leg.started is True

    manager.sync_recording_schedule([camera], now=datetime(2024, 1, 1, 10, 0))
    await asyncio.sleep(0)  # let the create_task'd stop() run
    assert record_leg.stopped is True


@pytest.mark.asyncio
async def test_sync_recording_schedule_ignores_cameras_without_a_schedule():
    from app.ffmpeg_manager import StreamManager

    manager = StreamManager.__new__(StreamManager)
    manager._legs = {}
    manager._configs = {}
    record_leg = FakeLeg()
    manager._legs["cam1"] = {"record": record_leg, "live": FakeLeg()}
    camera = FakeCamera(record_schedule=[])

    manager.sync_recording_schedule([camera])
    assert record_leg.started is False
    assert record_leg.stopped is False
