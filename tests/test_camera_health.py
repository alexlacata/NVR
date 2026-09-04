from app.camera_health import CameraHealthRegistry


def test_no_notification_before_offline_threshold(monkeypatch):
    fake_now = [0.0]
    monkeypatch.setattr("app.camera_health.time.monotonic", lambda: fake_now[0])
    registry = CameraHealthRegistry()

    went_offline, came_back = registry.observe("cam1", "error", offline_after_seconds=120)
    assert (went_offline, came_back) == (False, False)

    fake_now[0] += 60  # still under the 120s threshold
    went_offline, came_back = registry.observe("cam1", "error", offline_after_seconds=120)
    assert (went_offline, came_back) == (False, False)


def test_fires_offline_once_past_threshold_then_not_again(monkeypatch):
    fake_now = [0.0]
    monkeypatch.setattr("app.camera_health.time.monotonic", lambda: fake_now[0])
    registry = CameraHealthRegistry()

    registry.observe("cam1", "error", offline_after_seconds=120)
    fake_now[0] += 121
    went_offline, came_back = registry.observe("cam1", "error", offline_after_seconds=120)
    assert (went_offline, came_back) == (True, False)

    # still erroring - no repeat notification
    fake_now[0] += 60
    went_offline, came_back = registry.observe("cam1", "error", offline_after_seconds=120)
    assert (went_offline, came_back) == (False, False)


def test_fires_back_online_after_recovering_from_a_notified_offline(monkeypatch):
    fake_now = [0.0]
    monkeypatch.setattr("app.camera_health.time.monotonic", lambda: fake_now[0])
    registry = CameraHealthRegistry()

    registry.observe("cam1", "error", offline_after_seconds=120)
    fake_now[0] += 121
    registry.observe("cam1", "error", offline_after_seconds=120)  # fires offline

    went_offline, came_back = registry.observe("cam1", "running", offline_after_seconds=120)
    assert (went_offline, came_back) == (False, True)

    # recovering again without having been notified offline again -> no repeat
    went_offline, came_back = registry.observe("cam1", "running", offline_after_seconds=120)
    assert (went_offline, came_back) == (False, False)


def test_brief_error_blip_that_recovers_before_threshold_never_notifies(monkeypatch):
    fake_now = [0.0]
    monkeypatch.setattr("app.camera_health.time.monotonic", lambda: fake_now[0])
    registry = CameraHealthRegistry()

    registry.observe("cam1", "error", offline_after_seconds=120)
    fake_now[0] += 5
    went_offline, came_back = registry.observe("cam1", "running", offline_after_seconds=120)
    assert (went_offline, came_back) == (False, False)  # was never notified, so no "back online" either


def test_cameras_tracked_independently():
    registry = CameraHealthRegistry()
    went_offline_a, _ = registry.observe("cam1", "error", offline_after_seconds=0)
    went_offline_b, _ = registry.observe("cam2", "running", offline_after_seconds=0)
    assert went_offline_a is True
    assert went_offline_b is False
