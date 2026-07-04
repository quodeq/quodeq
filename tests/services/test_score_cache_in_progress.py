"""Regression: an in-progress run must not be persisted to the score cache.

Opening History (or its live refresh polling) while a scan is running used to
persist the run's *partial* scalar set -- e.g. only ``security`` of six. The
cache version hashes only dismissals/deletions/params, so the run completing
never invalidated that row: the history trend showed one dimension forever
while run-detail (which reads the run's evaluation output directly) showed all
six. Only terminal (complete) runs may be persisted.
"""
import sqlite3
from pathlib import Path

import pytest

from quodeq.services import _external_jobs
from quodeq.services.dashboard import clear_shared_dimension_cache
from quodeq.services.dismissed import dismiss_finding, dismissed_keys
from quodeq.services.scoring import get_project_scores
from tests.services._scalar_fixtures import build_projected_run


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    clear_shared_dimension_cache()
    yield
    clear_shared_dimension_cache()


def _cached_run_ids(cache_path: Path) -> dict[str, int]:
    """Map run_id -> number of persisted scalar rows in the score cache."""
    if not cache_path.exists():
        return {}
    conn = sqlite3.connect(cache_path)
    try:
        rows = conn.execute(
            "SELECT run_id, COUNT(*) FROM run_scalars GROUP BY run_id"
        ).fetchall()
    finally:
        conn.close()
    return {rid: n for rid, n in rows}


def test_in_progress_run_not_persisted_but_complete_run_is(tmp_path, monkeypatch):
    reports = tmp_path / "evaluations"
    # A finished run (persists normally) and a still-running run (must not persist).
    build_projected_run(reports, "proj", "20260101T000000", {"security": (7.0, "Fair")})
    live_run = "20260102T000000"
    build_projected_run(reports, "proj", live_run, {"security": (8.0, "Good")})
    dismiss_finding(reports / "proj", {"req": "R1", "file": "a.py", "line": 1})
    assert dismissed_keys(reports / "proj"), "heavy (cached) path not activated"

    # Make the newer run look live: resolve_external_pid returns a pid for it.
    def fake_pid(project, run_id, root):
        return 4242 if run_id == live_run else None
    monkeypatch.setattr(_external_jobs, "resolve_external_pid", fake_pid)

    scores = get_project_scores(reports, "proj")
    trend_ids = {e["runId"] for e in scores["trend"]}
    assert live_run in trend_ids, "in-progress run should still be served in the trend"

    cached = _cached_run_ids(tmp_path / "sc.db")
    assert cached.get("20260101T000000") == 1, "completed run should be persisted"
    assert live_run not in cached, (
        "in-progress run must NOT be persisted -- its partial scalar set would be "
        "served forever after the run completes"
    )
