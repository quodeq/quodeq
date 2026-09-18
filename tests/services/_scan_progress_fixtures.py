"""Shared run-dir builders for tests/services/test_scan_progress*.py."""
from __future__ import annotations

import json
from pathlib import Path


def _write_status(run_dir: Path, *, dimensions: list[str], state: str = "running",
                  current_dimension: str | None = None) -> None:
    status = {
        "schema_version": 1,
        "job_id": "j1",
        "state": state,
        "started_at": "2026-04-26T12:00:00+00:00",
        "dimensions": dimensions,
        "phase": "analyzing",
        "current_dimension": current_dimension,
    }
    (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")


def _make_run(tmp_path: Path) -> Path:
    """Create a project_dir / run_dir layout with the directories the reader expects."""
    project_dir = tmp_path / "project"
    run_dir = project_dir / "run-1"
    (run_dir / "evidence").mkdir(parents=True)
    return run_dir
