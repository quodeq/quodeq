"""Tests for list_runs() run discovery and status detection."""
from pathlib import Path

import pytest


def test_list_runs_flags_in_progress_run(tmp_path: Path) -> None:
    """A run directory with manifest.json but no scan.json should be flagged in_progress."""
    from quodeq.data.fs.report_parser.runs import list_runs

    project_uuid = "proj-1"
    run_dir = tmp_path / project_uuid / "run-in-progress"
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "evidence" / "manifest.json").write_text("{}")
    (run_dir / "evaluation").mkdir()
    # Deliberately no scan.json

    runs = list_runs(tmp_path, project_uuid)
    assert len(runs) == 1
    assert runs[0].status == "in_progress"


def test_list_runs_flags_complete_run(tmp_path: Path) -> None:
    """A run directory with manifest.json and scan.json should be flagged complete."""
    from quodeq.data.fs.report_parser.runs import list_runs

    project_uuid = "proj-1"
    run_dir = tmp_path / project_uuid / "run-done"
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "evidence" / "manifest.json").write_text("{}")
    (run_dir / "evaluation").mkdir()
    (run_dir / "scan.json").write_text("{}")

    runs = list_runs(tmp_path, project_uuid)
    assert len(runs) == 1
    assert runs[0].status == "complete"


def test_list_runs_skips_empty_run_dirs(tmp_path: Path) -> None:
    """A directory with no manifest.json (pre-manifest abort) should not appear as a run."""
    from quodeq.data.fs.report_parser.runs import list_runs

    project_uuid = "proj-1"
    run_dir = tmp_path / project_uuid / "empty-run"
    run_dir.mkdir(parents=True)
    # no evidence/, no manifest.json, no scan.json

    runs = list_runs(tmp_path, project_uuid)
    assert len(runs) == 0


def test_list_runs_mixes_complete_and_in_progress(tmp_path: Path) -> None:
    """Both complete and in-progress runs coexist in the same project directory."""
    from quodeq.data.fs.report_parser.runs import list_runs

    project_uuid = "proj-2"
    project_dir = tmp_path / project_uuid

    # Complete run
    done_dir = project_dir / "run-done"
    (done_dir / "evidence").mkdir(parents=True)
    (done_dir / "evidence" / "manifest.json").write_text("{}")
    (done_dir / "evaluation").mkdir()
    (done_dir / "scan.json").write_text("{}")

    # In-progress run
    prog_dir = project_dir / "run-in-progress"
    (prog_dir / "evidence").mkdir(parents=True)
    (prog_dir / "evidence" / "manifest.json").write_text("{}")
    (prog_dir / "evaluation").mkdir()
    # no scan.json

    # Abandoned run (no manifest)
    abandoned_dir = project_dir / "run-abandoned"
    abandoned_dir.mkdir(parents=True)

    runs = list_runs(tmp_path, project_uuid)
    assert len(runs) == 2
    by_id = {r.run_id: r for r in runs}
    assert by_id["run-done"].status == "complete"
    assert by_id["run-in-progress"].status == "in_progress"
    assert "run-abandoned" not in by_id
