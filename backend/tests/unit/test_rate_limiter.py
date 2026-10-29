import pytest
from hypothesis import given, strategies as st

from types import SimpleNamespace

from fastapi import HTTPException

from backend.api import limits
from backend.api.limits import SlidingWindowLimiter


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


def test_hits_up_to_the_limit_are_allowed_and_the_next_is_not(clock):
    limiter = SlidingWindowLimiter(limit=3, window_seconds=60, clock=clock)

    assert [limiter.hit("ip:1") for _ in range(3)] == [None, None, None]
    assert limiter.hit("ip:1") == pytest.approx(60)


def test_the_wait_counts_down_to_when_the_oldest_hit_expires(clock):
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60, clock=clock)
    limiter.hit("k")
    clock.now += 10
    limiter.hit("k")
    clock.now += 5

    assert limiter.hit("k") == pytest.approx(45)  # the first hit leaves at +60


@pytest.mark.parametrize("elapsed, allowed", [(59.999, False), (60.0, True), (60.001, True)])
def test_a_hit_leaves_the_window_exactly_window_seconds_later(clock, elapsed, allowed):
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.hit("k")
    clock.now += elapsed

    assert (limiter.hit("k") is None) is allowed


def test_a_refused_hit_does_not_use_up_a_slot(clock):
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.hit("k")
    for _ in range(5):
        clock.now += 10
        limiter.hit("k")  # refused while the first is in the window
    clock.now = 1000 + 60

    assert limiter.hit("k") is None


def test_a_limit_of_zero_admits_nothing(clock):
    limiter = SlidingWindowLimiter(limit=0, window_seconds=60, clock=clock)
    assert limiter.hit("k") == 60


def test_keys_are_counted_separately(clock):
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.hit("session:a")

    assert limiter.hit("session:b") is None
    assert limiter.hit("session:a") is not None


def test_reset_forgets_everything(clock):
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.hit("k")
    limiter.reset()

    assert limiter.hit("k") is None


@given(gaps=st.lists(st.floats(min_value=0, max_value=30), min_size=1, max_size=60),
       limit=st.integers(min_value=1, max_value=5))
def test_no_window_ever_admits_more_than_the_limit(gaps, limit):
    clock = Clock()
    limiter = SlidingWindowLimiter(limit=limit, window_seconds=60, clock=clock)
    admitted = []
    for gap in gaps:
        clock.now += gap
        if limiter.hit("k") is None:
            admitted.append(clock.now)
    for i, start in enumerate(admitted):
        in_window = [t for t in admitted[i:] if t < start + 60]
        assert len(in_window) <= limit


@pytest.mark.parametrize("tracked, swept", [(3, False), (4, True)])
def test_idle_keys_are_dropped_once_more_than_the_cap_are_tracked(clock, monkeypatch, tracked, swept):
    monkeypatch.setattr(SlidingWindowLimiter, "MAX_TRACKED_KEYS", 3)
    limiter = SlidingWindowLimiter(limit=5, window_seconds=60, clock=clock)
    for n in range(tracked - 1):
        limiter.hit(f"old-{n}")
    clock.now += 61                       # every key so far is now idle
    limiter.hit("new")                    # tracked keys reach `tracked`

    assert ("old-0" in limiter._hits) is not swept
    assert "new" in limiter._hits         # a key with a live hit is never dropped


def test_a_key_whose_last_hit_is_exactly_one_window_old_counts_as_idle(clock, monkeypatch):
    monkeypatch.setattr(SlidingWindowLimiter, "MAX_TRACKED_KEYS", 1)
    limiter = SlidingWindowLimiter(limit=5, window_seconds=60, clock=clock)
    limiter.hit("old")
    clock.now += 60
    limiter.hit("new")

    assert "old" not in limiter._hits


# ── how a refusal reaches the client ─────────────────────────────────

@pytest.fixture
def one_per_minute(clock, monkeypatch):
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, clock=clock)
    monkeypatch.setattr(limits, "ip_limiter", limiter)
    return limiter


def request_from(host):
    return SimpleNamespace(client=SimpleNamespace(host=host) if host else None)


def test_each_client_address_has_its_own_allowance(one_per_minute):
    limits.limit_by_ip(request_from("10.0.0.1"))

    limits.limit_by_ip(request_from("10.0.0.2"))           # a different address: allowed
    with pytest.raises(HTTPException):
        limits.limit_by_ip(request_from("10.0.0.1"))       # the same address again: refused


def test_requests_with_no_known_address_share_one_allowance(one_per_minute):
    limits.limit_by_ip(request_from(None))

    with pytest.raises(HTTPException):
        limits.limit_by_ip(request_from(None))


@pytest.mark.parametrize("seconds_later, retry_after", [(59.8, "1"), (59.0, "1"), (30.0, "30"), (0.0, "60")])
def test_retry_after_is_whole_seconds_rounded_up_and_never_zero(one_per_minute, clock, seconds_later, retry_after):
    limits.limit_by_ip(request_from("10.0.0.1"))
    clock.now += seconds_later

    with pytest.raises(HTTPException) as refused:
        limits.limit_by_ip(request_from("10.0.0.1"))

    assert refused.value.status_code == 429
    assert refused.value.headers == {"Retry-After": retry_after}
    assert refused.value.detail == "Too many requests. Please wait a moment and try again."
