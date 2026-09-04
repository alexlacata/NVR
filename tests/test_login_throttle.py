import pytest

from app.login_throttle import LoginThrottle


def test_locks_after_max_attempts_and_reports_wait(monkeypatch):
    fake_now = [1000.0]
    monkeypatch.setattr("app.login_throttle.time.monotonic", lambda: fake_now[0])

    throttle = LoginThrottle(max_attempts=3, window_seconds=60, lockout_seconds=30)
    assert throttle.seconds_until_unlocked("bob") == 0

    for _ in range(3):
        throttle.record_failure("bob")

    assert throttle.seconds_until_unlocked("bob") == pytest.approx(30, abs=0.01)


def test_unlocks_after_lockout_expires(monkeypatch):
    fake_now = [1000.0]
    monkeypatch.setattr("app.login_throttle.time.monotonic", lambda: fake_now[0])

    throttle = LoginThrottle(max_attempts=2, window_seconds=60, lockout_seconds=30)
    throttle.record_failure("bob")
    throttle.record_failure("bob")
    assert throttle.seconds_until_unlocked("bob") > 0

    fake_now[0] += 31
    assert throttle.seconds_until_unlocked("bob") == 0


def test_success_resets_failure_count():
    throttle = LoginThrottle(max_attempts=3, window_seconds=60, lockout_seconds=30)
    throttle.record_failure("bob")
    throttle.record_failure("bob")
    throttle.record_success("bob")
    throttle.record_failure("bob")
    throttle.record_failure("bob")
    # only 2 failures since the reset - below the threshold of 3
    assert throttle.seconds_until_unlocked("bob") == 0


def test_usernames_are_tracked_independently_and_case_insensitively():
    throttle = LoginThrottle(max_attempts=2, window_seconds=60, lockout_seconds=30)
    throttle.record_failure("Bob")
    throttle.record_failure("bob")
    assert throttle.seconds_until_unlocked("BOB") > 0
    assert throttle.seconds_until_unlocked("alice") == 0


def test_old_failures_outside_window_do_not_count(monkeypatch):
    fake_now = [1000.0]
    monkeypatch.setattr("app.login_throttle.time.monotonic", lambda: fake_now[0])

    throttle = LoginThrottle(max_attempts=3, window_seconds=60, lockout_seconds=30)
    throttle.record_failure("bob")
    fake_now[0] += 61  # outside the window - counter should reset
    throttle.record_failure("bob")
    throttle.record_failure("bob")
    assert throttle.seconds_until_unlocked("bob") == 0
