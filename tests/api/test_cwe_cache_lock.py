"""Test that concurrent CWE cache expiry triggers exactly ONE reload (finding #235)."""
from __future__ import annotations

import threading
import time as _time

import pytest

import quodeq.api.standards_read_routes as _mod


@pytest.fixture(autouse=True)
def _reset_cache():
    _mod.reset_cwe_cache()
    yield
    _mod.reset_cwe_cache()


def test_reload_cwe_if_needed_exists():
    """_reload_cwe_if_needed must exist as the synchronized reload helper."""
    assert callable(_mod._reload_cwe_if_needed)


def test_concurrent_expiry_reloads_exactly_once():
    """Two threads racing at cache expiry must trigger exactly one loader call.

    Strategy: force cache expiry, then release both threads simultaneously
    using an event so both see the stale cache and race to reload.
    The lock inside _reload_cwe_if_needed must ensure only one reload happens.
    """
    call_count = 0
    # Slow down the loader so the second thread genuinely races.
    slow_start = threading.Event()
    load_started = threading.Event()

    def _loader():
        nonlocal call_count
        load_started.set()        # signal that loading has begun
        slow_start.wait(timeout=5)  # wait for test harness to let it proceed
        call_count += 1
        return [{"id": "CWE-79", "name": "XSS"}]

    # Force expiry.
    _mod._cwe_cache = None
    _mod._cwe_cache_time = 0.0

    results = []
    errors = []

    start_gate = threading.Barrier(3)  # main + 2 worker threads

    def _thread():
        try:
            start_gate.wait(timeout=5)  # all three release together
            result = _mod._reload_cwe_if_needed(_loader)
            results.append(result)
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=_thread)
    t2 = threading.Thread(target=_thread)
    t1.start()
    t2.start()

    # Release all three (main + 2 workers) simultaneously.
    start_gate.wait(timeout=5)
    # Let the loader proceed after threads are racing.
    slow_start.set()

    t1.join(timeout=10)
    t2.join(timeout=10)

    assert not errors, f"Thread errors: {errors}"
    assert call_count == 1, f"Expected exactly 1 reload, got {call_count}"
    assert len(results) == 2
    # Both threads must see the same cached result.
    assert results[0] == results[1] == [{"id": "CWE-79", "name": "XSS"}]
