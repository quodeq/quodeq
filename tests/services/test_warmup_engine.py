"""Warm-up engine: background recompute of per-project caches at boot.

Regression context: after an upgrade invalidates the score caches, the first
/api/projects used to run minutes of recompute inline. The engine moves that
work to a daemon thread; the projects route stays a pure read.
"""
from __future__ import annotations

import logging
import threading
import time

from quodeq.services.warmup import WarmupEngine
import pytest


@pytest.fixture
def make_engine():
    """Build engines and stop every worker thread at teardown.

    ``WarmupEngine.start`` spawns a daemon thread; a test that never stops it
    leaves the thread polling until the process exits, which under xdist
    means for the rest of the worker's life.
    """
    created: list[WarmupEngine] = []

    def _make(**kwargs) -> WarmupEngine:
        eng = WarmupEngine(**kwargs)
        created.append(eng)
        return eng

    yield _make
    for eng in created:
        eng.reset_for_tests()


def _wait_until(pred, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_start_enumerates_newest_first_and_processes_all(tmp_path, make_engine):
    order = []
    done = threading.Event()

    def warm(reports_dir, pid):
        order.append(pid)
        if len(order) == 3:
            done.set()

    listing = [("old", "2026-01-01"), ("newest", "2026-08-01"), ("mid", "2026-05-01")]
    eng = make_engine(warm_fn=warm, list_fn=lambda _rd: listing)
    eng.start(str(tmp_path))

    assert done.wait(5)
    assert order == ["newest", "mid", "old"]
    assert _wait_until(lambda: eng.snapshot()["active"] is False)
    snap = eng.snapshot()
    assert snap == {"active": False, "projectsDone": 3, "projectsTotal": 3, "currentProjectName": None}


def test_snapshot_is_none_before_start(tmp_path, make_engine):
    eng = make_engine(warm_fn=lambda *_: None, list_fn=lambda _rd: [])
    assert eng.snapshot() is None


def test_enqueue_is_noop_before_start_and_dedupes_while_queued(tmp_path, make_engine):
    release = threading.Event()
    seen = []

    def warm(reports_dir, pid):
        seen.append(pid)
        release.wait(5)

    eng = make_engine(warm_fn=warm, list_fn=lambda _rd: [])
    eng.enqueue("p1")  # before start: no-op, no crash
    eng.start(str(tmp_path))
    eng.enqueue("p1")
    eng.enqueue("p1")  # duplicate while queued/in-progress
    assert _wait_until(lambda: seen == ["p1"])
    eng.enqueue("p1")  # still in progress -> deduped
    release.set()
    assert _wait_until(lambda: eng.snapshot()["projectsDone"] == 1)
    assert seen == ["p1"]


def test_failing_project_does_not_stop_the_queue(tmp_path, make_engine):
    seen = []

    def warm(reports_dir, pid):
        seen.append(pid)
        if pid == "bad":
            raise RuntimeError("boom")

    eng = make_engine(warm_fn=warm, list_fn=lambda _rd: [("bad", "2026-08-01"), ("good", "2026-07-01")])
    eng.start(str(tmp_path))
    assert _wait_until(lambda: eng.snapshot() is not None and eng.snapshot()["projectsDone"] == 2)
    assert seen == ["bad", "good"]


def test_failed_id_is_backed_off_from_reenqueue(tmp_path, make_engine):
    calls = []

    def warm(reports_dir, pid):
        calls.append(pid)
        raise RuntimeError("boom")

    eng = make_engine(warm_fn=warm, list_fn=lambda _rd: [])
    eng.start(str(tmp_path))
    eng.enqueue("p1")
    assert _wait_until(lambda: len(calls) == 1)
    assert _wait_until(lambda: eng.snapshot()["active"] is False)
    eng.enqueue("p1")  # within the 60s backoff window -> ignored
    time.sleep(0.1)
    assert calls == ["p1"]


def test_progress_shows_current_project_while_working(tmp_path, make_engine):
    entered = threading.Event()
    release = threading.Event()

    def warm(reports_dir, pid):
        entered.set()
        release.wait(5)

    eng = make_engine(warm_fn=warm, list_fn=lambda _rd: [("p1", "2026-08-01")])
    eng.start(str(tmp_path))
    assert entered.wait(5)
    snap = eng.snapshot()
    assert snap["active"] is True
    assert snap["projectsTotal"] == 1
    assert snap["projectsDone"] == 0
    release.set()


def test_reset_for_tests_stops_worker_and_allows_restart(tmp_path, make_engine):
    """Verify reset_for_tests() actually joins the worker thread and allows restart."""
    calls = []
    release1 = threading.Event()
    release2 = threading.Event()

    def warm(reports_dir, pid):
        calls.append(pid)
        if pid == "p1":
            release1.wait(5)
        else:
            release2.wait(5)

    eng = make_engine(warm_fn=warm, list_fn=lambda _rd: [])
    eng.start(str(tmp_path))
    eng.enqueue("p1")
    assert _wait_until(lambda: calls == ["p1"])

    # Reset: stops the worker, clears state
    release1.set()
    eng.reset_for_tests()
    assert _wait_until(lambda: eng.snapshot() is None)

    # Restart: should spawn exactly one new worker
    eng.start(str(tmp_path))
    eng.enqueue("p2")
    assert _wait_until(lambda: calls == ["p1", "p2"])
    release2.set()
    assert _wait_until(lambda: eng.snapshot()["projectsDone"] == 1)
    assert calls == ["p1", "p2"]


def test_start_is_a_noop_when_score_cache_disabled(tmp_path, monkeypatch, make_engine):
    monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
    eng = make_engine(warm_fn=lambda *_: None, list_fn=lambda _rd: [("p1", "2026-08-01")])
    eng.start(str(tmp_path))
    assert eng.snapshot() is None


def test_default_warm_project_runs_against_a_real_project_dir(tmp_path, monkeypatch):
    """Smoke: the production warm_fn imports and executes end to end.

    Every other engine test injects warm_fn; a typo inside _warm_project
    would otherwise pass the suite and silently push every project into
    failure backoff in production."""
    from quodeq.services.warmup import _warm_project

    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    project = tmp_path / "proj"
    project.mkdir()
    (project / "repository_info.json").write_text('{"name": "proj"}', encoding="utf-8")

    _warm_project(str(tmp_path), "proj")  # must not raise


def test_start_survives_a_project_listing_failure(tmp_path, make_engine):
    """A real enumeration failure (e.g. a bad run directory tripping
    validate_path_segment, or a filesystem stat error) must not stop the
    engine from starting -- it just starts with an empty queue."""
    def boom(_rd):
        raise OSError("listing failed")

    eng = make_engine(warm_fn=lambda *_: None, list_fn=boom)
    eng.start(str(tmp_path))
    assert _wait_until(lambda: eng.snapshot() is not None)
    assert eng.snapshot()["projectsTotal"] == 0


def test_start_lets_an_out_of_scope_listing_error_propagate(tmp_path, make_engine):
    """A bug in the listing seam outside (OSError, ValueError) is a genuine
    defect and must surface at startup, not be silently absorbed."""
    def boom(_rd):
        raise RuntimeError("unexpected bug")

    eng = make_engine(warm_fn=lambda *_: None, list_fn=boom)
    with pytest.raises(RuntimeError, match="unexpected bug"):
        eng.start(str(tmp_path))


def test_display_name_failure_falls_back_to_the_project_id(tmp_path, make_engine, monkeypatch):
    """A bad/unreadable repository_info.json (or any (OSError, ValueError)
    from _project_display_name) must not crash the worker -- the progress
    display just falls back to the raw project id."""
    entered = threading.Event()
    release = threading.Event()

    def boom(_reports_dir, _project_id):
        raise ValueError("bad metadata")

    monkeypatch.setattr("quodeq.services.warmup._project_display_name", boom)

    def warm(reports_dir, pid):
        entered.set()
        release.wait(5)

    eng = make_engine(warm_fn=warm, list_fn=lambda _rd: [("p1", "2026-08-01")])
    eng.start(str(tmp_path))
    assert entered.wait(5)
    assert eng.snapshot()["currentProjectName"] == "p1"
    release.set()


def test_display_name_out_of_scope_error_logs_and_still_warms_the_next_project(
    tmp_path, make_engine, monkeypatch, caplog,
):
    """A bug outside (OSError, ValueError) must not kill the score-warmup
    thread: run_isolated (the sole statement in _worker's loop body) logs it
    at warning with a traceback and the worker keeps draining the queue."""
    def display_name_boom(_reports_dir, project_id):
        if project_id == "bad":
            raise AttributeError("unexpected bug")
        return project_id

    monkeypatch.setattr("quodeq.services.warmup._project_display_name", display_name_boom)
    seen = []

    def warm(reports_dir, pid):
        seen.append(pid)

    caplog.set_level(logging.WARNING, logger="quodeq.services.warmup")
    eng = make_engine(
        warm_fn=warm, list_fn=lambda _rd: [("bad", "2026-08-01"), ("good", "2026-07-01")],
    )
    eng.start(str(tmp_path))
    assert _wait_until(lambda: eng.snapshot() is not None and eng.snapshot()["projectsDone"] == 2)
    # "bad" aborts before warm_fn runs; "good" still warms -- the thread survived.
    assert seen == ["good"]

    matching = [r for r in caplog.records if "score warmup" in r.getMessage()]
    assert matching, [(r.levelname, r.getMessage()) for r in caplog.records]
    assert matching[0].levelno == logging.WARNING
    assert "bad" in matching[0].getMessage()
    assert "Traceback (most recent call last)" in caplog.text
    assert "AttributeError" in caplog.text


def test_bad_repository_info_json_does_not_kill_worker(tmp_path, make_engine):
    """Verify that invalid repository_info.json doesn't crash the worker."""
    import json

    # Create a project with invalid metadata (JSON list instead of dict)
    bad_dir = tmp_path / "bad_project"
    bad_dir.mkdir()
    (bad_dir / "repository_info.json").write_text(json.dumps(["item1", "item2"]))

    seen = []

    def warm(reports_dir, pid):
        seen.append(pid)

    eng = make_engine(
        warm_fn=warm,
        list_fn=lambda _rd: [("bad_project", "2026-08-01"), ("good_project", "2026-07-01")],
    )
    eng.start(str(tmp_path))
    # Worker should process both, despite bad_project having invalid metadata
    assert _wait_until(lambda: eng.snapshot() is not None and eng.snapshot()["projectsDone"] == 2)
    assert seen == ["bad_project", "good_project"]
