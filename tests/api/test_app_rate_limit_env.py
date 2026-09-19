"""A malformed rate-limit env var must fall back, not crash the store build.

The window/cap are read inside ``_build_rate_limit_store`` from its ``env``
parameter, so a value is picked up per call rather than frozen at import.

Asserted through the store's own protocol (``check_and_record(ip, now)``),
never its attributes: the cap is how many calls pass before one is rejected,
and the window is how far ``now`` must advance before a rejected caller is
let through again. Both ``check`` and ``record`` take ``now`` explicitly, so
no clock patching is needed.
"""
from __future__ import annotations

from quodeq.api.app import (
    _DEFAULT_EVALUATION_RATE_LIMIT_MAX,
    _DEFAULT_EVALUATION_RATE_LIMIT_WINDOW,
    _build_rate_limit_store,
)

_IP = "203.0.113.7"


def _eval_store(env=None):
    _api_store, eval_store = _build_rate_limit_store(env=env)
    return eval_store


def _accepted_before_rejection(store, *, now: float = 0.0) -> int:
    """How many calls at *now* the store takes before it rejects one."""
    accepted = 0
    while not store.check_and_record(_IP, now):
        accepted += 1
        if accepted > 1000:  # pragma: no cover - guards a broken store
            raise AssertionError("store never rejected a request")
    return accepted


def _observed_window(store) -> float:
    """The smallest elapsed time that lets a rejected caller through again.

    Probed upwards rather than by bisection: ``check`` drops the timestamps
    it finds expired, so the first call that answers False also clears the
    state the probe is measuring.
    """
    _accepted_before_rejection(store)
    elapsed = 1
    while store.check(_IP, float(elapsed)):
        elapsed += 1
        if elapsed > 100_000:  # pragma: no cover - guards a broken store
            raise AssertionError("store never released the caller")
    return elapsed


def test_malformed_rate_limit_window_falls_back_to_default():
    store = _eval_store({"QUODEQ_RATE_LIMIT_WINDOW": "not-a-number"})
    assert _observed_window(store) == _DEFAULT_EVALUATION_RATE_LIMIT_WINDOW
    assert _accepted_before_rejection(_eval_store({"QUODEQ_RATE_LIMIT_WINDOW": "not-a-number"})) == (
        _DEFAULT_EVALUATION_RATE_LIMIT_MAX
    )


def test_malformed_rate_limit_max_falls_back_to_default():
    store = _eval_store({"QUODEQ_RATE_LIMIT_MAX": ""})
    assert _accepted_before_rejection(store) == _DEFAULT_EVALUATION_RATE_LIMIT_MAX
    assert _observed_window(_eval_store({"QUODEQ_RATE_LIMIT_MAX": ""})) == (
        _DEFAULT_EVALUATION_RATE_LIMIT_WINDOW
    )


def test_valid_rate_limit_env_vars_parse_unchanged():
    store = _eval_store({"QUODEQ_RATE_LIMIT_WINDOW": "60", "QUODEQ_RATE_LIMIT_MAX": "2"})
    # Two requests pass, the third is rejected.
    assert store.check_and_record(_IP, 0.0) is False
    assert store.check_and_record(_IP, 0.0) is False
    assert store.check_and_record(_IP, 0.0) is True
    # Still rejected just inside the 60s window, allowed once it has passed.
    assert store.check_and_record(_IP, 59.0) is True
    assert store.check_and_record(_IP, 60.0) is False


def test_injected_empty_env_ignores_the_host_environment(monkeypatch):
    """``env={}`` must not silently fall back to ``os.environ``."""
    monkeypatch.setenv("QUODEQ_RATE_LIMIT_WINDOW", "77")
    monkeypatch.setenv("QUODEQ_RATE_LIMIT_MAX", "3")
    monkeypatch.setenv("QUODEQ_RATE_LIMIT_BACKEND", "file")
    api_store, eval_store = _build_rate_limit_store(env={})
    assert _accepted_before_rejection(eval_store) == _DEFAULT_EVALUATION_RATE_LIMIT_MAX
    assert _observed_window(eval_store) == _DEFAULT_EVALUATION_RATE_LIMIT_WINDOW
    # The backend lookup is injected too: "file" in the host env must not win.
    assert type(api_store).__name__ == "InMemoryRateLimitStore"


def test_call_time_read_picks_up_a_later_value(monkeypatch):
    """No import-time freeze: a value set after import is still honoured."""
    monkeypatch.setenv("QUODEQ_RATE_LIMIT_MAX", "1")
    monkeypatch.delenv("QUODEQ_RATE_LIMIT_WINDOW", raising=False)
    assert _accepted_before_rejection(_eval_store()) == 1
