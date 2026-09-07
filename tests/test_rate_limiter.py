import time

from app.rate_limiter import RateLimiter


def test_allows_up_to_the_limit():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    for _ in range(3):
        allowed, retry_after = limiter.allow("ip:1.2.3.4")
        assert allowed is True
        assert retry_after == 0.0


def test_blocks_beyond_the_limit():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    for _ in range(3):
        limiter.allow("ip:1.2.3.4")
    allowed, retry_after = limiter.allow("ip:1.2.3.4")
    assert allowed is False
    assert retry_after > 0


def test_different_keys_have_independent_budgets():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.allow("ip:1.2.3.4")[0] is True
    assert limiter.allow("ip:1.2.3.4")[0] is False
    assert limiter.allow("user:alice")[0] is True


def test_resets_after_the_window_elapses():
    limiter = RateLimiter(max_requests=1, window_seconds=0.05)
    assert limiter.allow("ip:1.2.3.4")[0] is True
    assert limiter.allow("ip:1.2.3.4")[0] is False
    time.sleep(0.06)
    assert limiter.allow("ip:1.2.3.4")[0] is True


def test_prune_drops_only_expired_windows():
    limiter = RateLimiter(max_requests=5, window_seconds=0.05)
    limiter.allow("ip:stale")
    time.sleep(0.06)
    limiter.allow("ip:fresh")
    limiter._prune(time.monotonic())
    assert "ip:stale" not in limiter._windows
    assert "ip:fresh" in limiter._windows
