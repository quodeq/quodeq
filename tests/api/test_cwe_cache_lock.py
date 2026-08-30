"""Test that concurrent CWE cache expiry triggers exactly ONE reload (finding #235)."""
from __future__ import annotations

import threading
import time as _time

import pytest

from quodeq.api.standards_read_routes import CweCache
from tests._timeouts import budget


def test_cwe_cache_get_exists():
    """CweCache.get must exist as the synchronized reload method."""
    assert callable(CweCache().get)


def test_concurrent_expiry_reloads_exactly_once():
    """Two threads racing at cache expiry must trigger exactly one loader call.

    Strategy: force cache expiry, then release both threads simultaneously
    using an event so both see the stale cache and race to reload.
    The lock inside CweCache.get must ensure only one reload happens.
    """
    call_count = 0
    # Slow down the loader so the second thread genuinely races.
    slow_start = threading.Event()
    load_started = threading.Event()

    def _loader():
        nonlocal call_count
        load_started.set()        # signal that loading has begun
        slow_start.wait(timeout=budget(5))  # wait for test harness to let it proceed
        call_count += 1
        return [{"id": "CWE-79", "name": "XSS"}]

    # Force expiry.
    cache = CweCache(ttl_s=3600)
    cache._cache = None
    cache._cache_time = 0.0

    results = []
    errors = []

    start_gate = threading.Barrier(3)  # main + 2 worker threads

    def _thread():
        try:
            start_gate.wait(timeout=budget(5))  # all three release together
            result = cache.get(_loader)
            results.append(result)
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=_thread)
    t2 = threading.Thread(target=_thread)
    t1.start()
    t2.start()

    # Release all three (main + 2 workers) simultaneously.
    start_gate.wait(timeout=budget(5))
    # Let the loader proceed after threads are racing.
    slow_start.set()

    t1.join(timeout=budget(10))
    t2.join(timeout=budget(10))

    assert not errors, f"Thread errors: {errors}"
    assert call_count == 1, f"Expected exactly 1 reload, got {call_count}"
    assert len(results) == 2
    # Both threads must see the same cached result.
    assert results[0] == results[1] == [{"id": "CWE-79", "name": "XSS"}]


def test_ttl_defaults_from_env_per_instance(monkeypatch):
    """TTL is read from QUODEQ_CWE_CACHE_TTL at construction time, per instance."""
    monkeypatch.setenv("QUODEQ_CWE_CACHE_TTL", "42")
    assert CweCache()._ttl_s == 42


def test_explicit_ttl_overrides_env(monkeypatch):
    monkeypatch.setenv("QUODEQ_CWE_CACHE_TTL", "42")
    assert CweCache(ttl_s=7)._ttl_s == 7


def test_clear_forces_a_reload():
    calls = []

    def _loader():
        calls.append(1)
        return ["x"]

    cache = CweCache()
    cache.get(_loader)
    cache.get(_loader)
    assert len(calls) == 1
    cache.clear()
    cache.get(_loader)
    assert len(calls) == 2


def test_injectable_clock_controls_expiry():
    now = [0.0]
    cache = CweCache(ttl_s=10, clock=lambda: now[0])
    calls = []

    def _loader():
        calls.append(1)
        return ["x"]

    cache.get(_loader)
    now[0] = 5.0  # still within TTL
    cache.get(_loader)
    assert len(calls) == 1
    now[0] = 11.0  # expired
    cache.get(_loader)
    assert len(calls) == 2
