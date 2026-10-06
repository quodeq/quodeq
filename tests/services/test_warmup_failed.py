"""The engine remembers which projects its last warm failed, until one succeeds.

Regression context: a shared project whose warm-up raised was discarded from
the queue while its card stayed pending, so the shared listing kept hiding it
with no signal. The listing now asks the engine whether the warm failed, and
a later successful warm must clear that mark.
"""
from __future__ import annotations

import time

from quodeq.services import warmup
from quodeq.services.warmup import WarmupEngine


def _wait_until(pred, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_failed_is_true_after_a_raising_warm_and_cleared_by_a_later_success(tmp_path, monkeypatch):
    outcomes = iter([RuntimeError("corrupt run"), None])

    def warm(reports_dir, pid):
        exc = next(outcomes)
        if exc is not None:
            raise exc
    monkeypatch.setattr(warmup, "_FAILURE_BACKOFF_S", 0.0)
    engine = WarmupEngine(warm_fn=warm, list_fn=lambda _rd: [])
    try:
        engine.start(str(tmp_path))
        assert engine.failed("p") is False

        engine.enqueue("p")
        assert _wait_until(lambda: engine.snapshot()["active"] is False and engine.failed("p"))

        engine.enqueue("p")
        assert _wait_until(lambda: engine.snapshot()["projectsDone"] == 2)
        assert engine.failed("p") is False
    finally:
        engine.reset_for_tests()
