"""The dimensions of a project's most recent finished run, for the setup card's preselection."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.services.latest_run_dims import latest_run_dimensions


def _run(project_dir: Path, run_id: str, *, state: str, dims: list[str], started: str) -> None:
    run = project_dir / run_id
    run.mkdir(parents=True)
    (run / "status.json").write_text(json.dumps({
        "schema_version": 2, "job_id": f"ext-{run_id}", "state": state,
        "started_at": started, "dimensions": dims,
    }))


def test_newest_finished_run_wins(tmp_path):
    proj = tmp_path / "p"
    _run(proj, "r-old", state="done", dims=["security"], started="2026-10-01T10:00:00+00:00")
    _run(proj, "r-new", state="done", dims=["security", "usability"], started="2026-10-05T10:00:00+00:00")
    assert latest_run_dimensions(tmp_path, "p") == ["security", "usability"]


def test_running_and_failed_runs_are_skipped(tmp_path):
    proj = tmp_path / "p"
    _run(proj, "r-done", state="done", dims=["reliability"], started="2026-10-01T10:00:00+00:00")
    _run(proj, "r-running", state="running", dims=["security"], started="2026-10-06T10:00:00+00:00")
    _run(proj, "r-failed", state="failed", dims=["usability"], started="2026-10-05T10:00:00+00:00")
    assert latest_run_dimensions(tmp_path, "p") == ["reliability"]


def test_no_runs_or_no_project_is_empty(tmp_path):
    (tmp_path / "p").mkdir()
    assert latest_run_dimensions(tmp_path, "p") == []
    assert latest_run_dimensions(tmp_path, "missing") == []
