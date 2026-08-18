"""Warm-up engine: background recompute of per-project caches at boot.

Regression context: after an upgrade invalidates the score caches, the first
/api/projects used to run minutes of recompute inline. The engine moves that
work to a daemon thread; the projects route stays a pure read.
"""
from __future__ import annotations

import threading
import time

from quodeq.services._warmup import WarmupEngine


def _wait_until(pred, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_start_enumerates_newest_first_and_processes_all(tmp_path):
    order = []
    done = threading.Event()

    def warm(reports_dir, pid):
        order.append(pid)
        if len(order) == 3:
            done.set()

    listing = [("old", "2026-01-01"), ("newest", "2026-08-01"), ("mid", "2026-05-01")]
    eng = WarmupEngine(warm_fn=warm, list_fn=lambda _rd: listing)
    eng.start(str(tmp_path))

    assert done.wait(5)
    assert order == ["newest", "mid", "old"]
    assert _wait_until(lambda: eng.snapshot()["active"] is False)
    snap = eng.snapshot()
    assert snap == {"active": False, "projectsDone": 3, "projectsTotal": 3, "currentProjectName": None}


def test_snapshot_is_none_before_start(tmp_path):
    eng = WarmupEngine(warm_fn=lambda *_: None, list_fn=lambda _rd: [])
    assert eng.snapshot() is None


def test_enqueue_is_noop_before_start_and_dedupes_while_queued(tmp_path):
    release = threading.Event()
    seen = []

    def warm(reports_dir, pid):
        seen.append(pid)
        release.wait(5)

    eng = WarmupEngine(warm_fn=warm, list_fn=lambda _rd: [])
    eng.enqueue("p1")  # before start: no-op, no crash
    eng.start(str(tmp_path))
    eng.enqueue("p1")
    eng.enqueue("p1")  # duplicate while queued/in-progress
    assert _wait_until(lambda: seen == ["p1"])
    eng.enqueue("p1")  # still in progress -> deduped
    release.set()
    assert _wait_until(lambda: eng.snapshot()["projectsDone"] == 1)
    assert seen == ["p1"]


def test_failing_project_does_not_stop_the_queue(tmp_path):
    seen = []

    def warm(reports_dir, pid):
        seen.append(pid)
        if pid == "bad":
            raise RuntimeError("boom")

    eng = WarmupEngine(warm_fn=warm, list_fn=lambda _rd: [("bad", "2026-08-01"), ("good", "2026-07-01")])
    eng.start(str(tmp_path))
    assert _wait_until(lambda: eng.snapshot() is not None and eng.snapshot()["projectsDone"] == 2)
    assert seen == ["bad", "good"]


def test_failed_id_is_backed_off_from_reenqueue(tmp_path):
    calls = []

    def warm(reports_dir, pid):
        calls.append(pid)
        raise RuntimeError("boom")

    eng = WarmupEngine(warm_fn=warm, list_fn=lambda _rd: [])
    eng.start(str(tmp_path))
    eng.enqueue("p1")
    assert _wait_until(lambda: len(calls) == 1)
    assert _wait_until(lambda: eng.snapshot()["active"] is False)
    eng.enqueue("p1")  # within the 60s backoff window -> ignored
    time.sleep(0.1)
    assert calls == ["p1"]


def test_progress_shows_current_project_while_working(tmp_path):
    entered = threading.Event()
    release = threading.Event()

    def warm(reports_dir, pid):
        entered.set()
        release.wait(5)

    eng = WarmupEngine(warm_fn=warm, list_fn=lambda _rd: [("p1", "2026-08-01")])
    eng.start(str(tmp_path))
    assert entered.wait(5)
    snap = eng.snapshot()
    assert snap["active"] is True
    assert snap["projectsTotal"] == 1
    assert snap["projectsDone"] == 0
    release.set()
