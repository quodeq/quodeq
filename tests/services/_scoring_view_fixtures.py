"""Shared run/eval builders for tests/services/test_scoring_view*.py."""
from __future__ import annotations

import json
from pathlib import Path


# Each test gets a unique date per run_id so list_runs can sort newest-first.
_RUN_DATES = {
    "run1": "2026-01-01T10:00:00",
    "run2": "2026-02-01T10:00:00",
    "run3": "2026-03-01T10:00:00",
    "r1":   "2026-01-01T10:00:00",
    "r2":   "2026-02-01T10:00:00",
}


def _ensure_run_dir(project_dir: Path, run_id: str) -> Path:
    """Create a run dir with the manifest.json that ``list_runs`` needs to
    register the run as a project entry."""
    run_dir = project_dir / run_id
    evidence = run_dir / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "manifest.json").write_text("{}")
    return run_dir


def _write_eval(
    project_dir: Path, run_id: str, dim_id: str,
    *, files_read: int = 100, score: str = "8.0/10", grade: str = "Good",
) -> None:
    _ensure_run_dir(project_dir, run_id)
    eval_dir = project_dir / run_id / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / f"{dim_id}.json").write_text(json.dumps({
        "dimension": dim_id,
        "date": _RUN_DATES.get(run_id, "2026-01-01T10:00:00"),
        "filesRead": files_read,
        "overallScore": score,
        "overallGrade": grade,
    }))


def _write_status(project_dir: Path, run_id: str, *, state: str) -> None:
    run_dir = project_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "status.json").write_text(json.dumps({"state": state}))
