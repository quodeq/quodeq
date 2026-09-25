"""LogThrottle: a lock-free, best-effort cooldown for one log call site.

Characterizes the semantics api/security.py's CSP-failure logging used to
get from a bare module global (``_last_csp_ws_failure_log_at``): the first
call always emits, a repeat inside the interval is dropped, and a repeat
once the interval has elapsed emits again.
"""
from __future__ import annotations

from quodeq.shared.log_throttle import LogThrottle


def test_first_call_always_emits():
    throttle = LogThrottle(60.0)
    assert throttle.should_emit(100.0) is True


def test_repeat_within_the_interval_is_dropped():
    throttle = LogThrottle(60.0)
    assert throttle.should_emit(100.0) is True
    assert throttle.should_emit(100.0 + 59.9) is False


def test_repeat_once_the_interval_elapses_emits_again():
    throttle = LogThrottle(60.0)
    assert throttle.should_emit(100.0) is True
    assert throttle.should_emit(160.0) is True  # exactly one interval later


def test_emits_once_per_interval_across_many_calls():
    """A sustained failure logs once per interval, not once per call."""
    throttle = LogThrottle(10.0)
    now = 0.0
    emitted = 0
    for _ in range(50):
        if throttle.should_emit(now):
            emitted += 1
        now += 1.0  # 50 calls, 1s apart, over a 10s interval

    assert emitted == 5, f"expected one emission per 10s interval, got {emitted}"


def test_a_low_uptime_clock_still_emits_the_first_failure():
    """*now* is typically time.monotonic() (seconds since boot). A machine
    up for less than the interval must not silently drop the first
    emission -- guards against a bare ``0.0`` "never emitted" sentinel.
    """
    throttle = LogThrottle(60.0)
    assert throttle.should_emit(5.0) is True