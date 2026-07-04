"""#1389 - _project_all_runs must run off the request thread with dedup lock.

Two concurrent POST /api/findings/dismiss calls for the same project (without
a usable run_id) must NOT run two concurrent projections. The per-project
non-blocking lock ensures the second caller skips if one is already running.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import patch, MagicMock

import pytest
from flask import Flask

from quodeq.api.routes_findings import register_findings_routes
from quodeq.services.mutation_rescore import _projection_locks


@pytest.fixture()
def app(tmp_path):
    a = Flask(__name__)
    a.config["TESTING"] = True
    a.config["EVALUATIONS_DIR"] = str(tmp_path)
    register_findings_routes(a)
    return a


@pytest.fixture()
def client(app):
    return app.test_client()


def test_dismiss_returns_without_waiting_for_projection(client, tmp_path):
    """POST /dismiss returns 200 without blocking on _project_all_runs."""
    (tmp_path / "my-project").mkdir()

    projection_started = threading.Event()
    projection_may_finish = threading.Event()

    def _slow_project(project_dir):
        projection_started.set()
        projection_may_finish.wait(timeout=5)

    with patch(
        "quodeq.services.mutation_rescore._project_all_runs",
        side_effect=_slow_project,
    ):
        resp = client.post("/api/findings/dismiss", json={
            "project": "my-project",
            "req": "M-MOD-1",
            "file": "foo.py",
            "line": 1,
        })

    # Response must arrive before the projection finishes.
    assert resp.status_code == 200

    # Unblock background thread.
    projection_may_finish.set()

    # Confirm the thread was actually launched.
    assert projection_started.wait(timeout=2), (
        "Background projection thread never started."
    )


def test_concurrent_dismisses_same_project_call_project_all_runs_once(
    tmp_path,
):
    """Two simultaneous dismiss POSTs for the same project run projection once.

    The per-project non-blocking lock causes the second background thread to
    skip projection when the first is still running.
    """
    # Clear any leftover lock state from previous tests.
    _projection_locks.clear()

    (tmp_path / "proj").mkdir()

    a = Flask(__name__)
    a.config["TESTING"] = True
    a.config["EVALUATIONS_DIR"] = str(tmp_path)
    register_findings_routes(a)
    client = a.test_client()

    call_count = 0
    projection_first_started = threading.Event()
    projection_first_may_finish = threading.Event()

    def _blocking_project(project_dir):
        nonlocal call_count
        call_count += 1
        projection_first_started.set()
        # Hold the lock while the second request fires.
        projection_first_may_finish.wait(timeout=5)

    with patch(
        "quodeq.services.mutation_rescore._project_all_runs",
        side_effect=_blocking_project,
    ):
        # Fire first request and wait until projection has started (lock held).
        r1 = client.post("/api/findings/dismiss", json={
            "project": "proj", "req": "R1", "file": "a.py", "line": 1,
        })
        assert projection_first_started.wait(timeout=2), (
            "First projection never started."
        )

        # Fire second request while first projection holds the lock.
        r2 = client.post("/api/findings/dismiss", json={
            "project": "proj", "req": "R2", "file": "b.py", "line": 2,
        })

        # Allow first projection to finish.
        projection_first_may_finish.set()

        # Give background threads a moment to settle.
        time.sleep(0.1)

    assert r1.status_code == 200
    assert r2.status_code == 200

    assert call_count == 1, (
        f"Expected _project_all_runs to be called exactly once for the same "
        f"project (second caller should skip via non-blocking acquire), "
        f"but it was called {call_count} time(s)."
    )
