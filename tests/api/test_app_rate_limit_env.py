"""A malformed rate-limit env var must fall back, not crash the store build.

The window/cap are read inside ``_build_rate_limit_store`` from its ``env``
parameter, so a value is picked up per call rather than frozen at import.
"""
from __future__ import annotations

from quodeq.api.app import _build_rate_limit_store


def _eval_store(env):
    _api_store, eval_store = _build_rate_limit_store(env=env)
    return eval_store


def test_malformed_rate_limit_window_falls_back_to_default():
    store = _eval_store({"QUODEQ_RATE_LIMIT_WINDOW": "not-a-number"})
    assert store._window == 300
    assert store._max_requests == 10


def test_malformed_rate_limit_max_falls_back_to_default():
    store = _eval_store({"QUODEQ_RATE_LIMIT_MAX": ""})
    assert store._max_requests == 10
    assert store._window == 300


def test_valid_rate_limit_env_vars_parse_unchanged():
    store = _eval_store({"QUODEQ_RATE_LIMIT_WINDOW": "60", "QUODEQ_RATE_LIMIT_MAX": "5"})
    assert store._window == 60
    assert store._max_requests == 5


def test_injected_empty_env_ignores_the_host_environment(monkeypatch):
    """``env={}`` must not silently fall back to ``os.environ``."""
    monkeypatch.setenv("QUODEQ_RATE_LIMIT_WINDOW", "77")
    monkeypatch.setenv("QUODEQ_RATE_LIMIT_MAX", "3")
    monkeypatch.setenv("QUODEQ_RATE_LIMIT_BACKEND", "file")
    api_store, eval_store = _build_rate_limit_store(env={})
    assert eval_store._window == 300
    assert eval_store._max_requests == 10
    # The backend lookup is injected too: "file" in the host env must not win.
    assert type(api_store).__name__ == "InMemoryRateLimitStore"


def test_call_time_read_picks_up_a_later_value(monkeypatch):
    """No import-time freeze: a value set after import is still honoured."""
    monkeypatch.setenv("QUODEQ_RATE_LIMIT_WINDOW", "123")
    _api_store, eval_store = _build_rate_limit_store()
    assert eval_store._window == 123
