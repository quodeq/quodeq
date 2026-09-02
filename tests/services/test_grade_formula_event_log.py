"""Tests for grade-formula's _event_log_runs ordering.

Split from test_grade_formula.py.

Regression: run ordering must use started_at, not dir mtime. And a
future/unsupported status.json schema_version must not crash ordering.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


def _write_status_json(run_dir: Path, started_at: str) -> None:
    """Write a minimal valid status.json fixture into *run_dir*."""
    payload = {
        "schema_version": 2,
        "job_id": run_dir.name,
        "state": "done",
        "started_at": started_at,
        "updated_at": started_at,
        "finalized_at": started_at,
        "phase": None,
        "current_dimension": None,
        "dimensions": [],
        "pid": 1,
        "exit_reason": None,
        "deadline_at": None,
    }
    (run_dir / "status.json").write_text(json.dumps(payload), encoding="utf-8")


def test_event_log_runs_orders_by_started_at_not_mtime(tmp_path):
    """Older started_at run must not win just because its dir mtime is bumped.

    Scenario: run_old was created earlier (lower started_at) but we
    artificially advance its directory mtime so it looks newer to a naive
    mtime sort.  _event_log_runs must still return run_new first.
    """
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    run_old = project_dir / "run_old"
    run_old.mkdir()
    (run_old / "events.jsonl").write_text("")
    _write_status_json(run_old, "2024-01-01T10:00:00+00:00")

    run_new = project_dir / "run_new"
    run_new.mkdir()
    (run_new / "events.jsonl").write_text("")
    _write_status_json(run_new, "2024-06-01T10:00:00+00:00")

    # Bump run_old's mtime to "now + 1 hour" so a naive mtime sort would pick it.
    future_ts = time.time() + 3600
    os.utime(run_old, (future_ts, future_ts))

    from quodeq.services.grade_formula import _event_log_runs  # noqa: PLC0415

    ordered = _event_log_runs(project_dir)
    assert ordered[0] == run_new, (
        f"Expected run_new (newer started_at) first, got {ordered[0].name}"
    )


def test_event_log_runs_tolerates_future_schema_version(tmp_path):
    """A run whose status.json has a schema_version newer than supported must
    not raise; it falls back to mtime ordering and the other runs are unaffected.
    """
    from quodeq.data.fs.run_status_store import SCHEMA_VERSION
    from quodeq.services.grade_formula import _event_log_runs  # noqa: PLC0415

    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    # A normal run with a known-good status.json.
    run_good = project_dir / "run_good"
    run_good.mkdir()
    (run_good / "events.jsonl").write_text("")
    _write_status_json(run_good, "2024-06-01T10:00:00+00:00")

    # A run with a status.json whose schema_version is far above supported.
    run_future = project_dir / "run_future"
    run_future.mkdir()
    (run_future / "events.jsonl").write_text("")
    future_payload = {
        "schema_version": SCHEMA_VERSION + 99,
        "job_id": "run_future",
        "state": "done",
        "started_at": "2024-03-01T10:00:00+00:00",
    }
    (run_future / "status.json").write_text(json.dumps(future_payload), encoding="utf-8")

    # Must not raise — and both runs must be present in the result.
    ordered = _event_log_runs(project_dir)
    names = [r.name for r in ordered]
    assert "run_good" in names, "run_good must be included"
    assert "run_future" in names, "run_future must be included (mtime fallback)"
    # run_good has a proper started_at key (priority 1); run_future uses mtime
    # fallback (priority 0) so run_good always sorts first regardless of mtime.
    assert ordered[0].name == "run_good", (
        f"run_good (proper started_at) should sort first, got {ordered[0].name}"
    )
