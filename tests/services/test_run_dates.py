import json
from pathlib import Path

from quodeq.services.run_dates import project_run_dates


def _write_status(run_dir: Path, started_at: str):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "status.json").write_text(json.dumps({
        "schema_version": 1, "job_id": f"job-{run_dir.name}", "state": "done",
        "started_at": started_at, "updated_at": started_at, "finalized_at": started_at,
        "phase": None, "current_dimension": None, "dimensions": [], "pid": None,
        "exit_reason": None, "deadline_at": None,
    }), encoding="utf-8")


def test_returns_normalized_dates_from_index(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "idx.db"))
    reports = tmp_path / "evaluations"
    _write_status(reports / "proj" / "run-a", "2026-05-25T22:19:50+00:00")

    dates = project_run_dates(reports, "proj")
    # normalize_date on an ISO datetime -> (utc iso + 'Z', "25 May 2026")
    assert dates["run-a"] == ("2026-05-25T22:19:50Z", "25 May 2026")


def test_bad_index_returns_empty(tmp_path, monkeypatch):
    # Point the index at a path that is a directory -> sqlite/open error -> {}.
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path))
    assert project_run_dates(tmp_path / "evaluations", "proj") == {}
