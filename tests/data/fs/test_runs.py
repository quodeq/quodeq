"""Tests for list_runs() run discovery and status detection."""
import os
from pathlib import Path


def test_list_runs_marks_in_progress_when_pid_is_live(tmp_path: Path) -> None:
    """A run with a live .pid file should be flagged in_progress."""
    from quodeq.data.fs.report_parser.runs import list_runs

    project_uuid = "proj-1"
    run_dir = tmp_path / project_uuid / "run-live"
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "evidence" / "manifest.json").write_text("{}")
    (run_dir / "evaluation").mkdir()
    # Write our own PID — the liveness check passes for os.getpid()
    (run_dir / ".pid").write_text(str(os.getpid()))

    runs = list_runs(tmp_path, project_uuid)
    assert len(runs) == 1
    assert runs[0].status == "in_progress"


def test_list_runs_marks_historical_runs_as_complete(tmp_path: Path) -> None:
    """A historical run (manifest present, no live PID) shows as complete in History.

    This preserves visibility of all past runs regardless of whether they
    completed cleanly — the dashboard's job is to show the user everything
    they've evaluated, and completion state is inferred from scored output
    in the UI, not from a filesystem marker.
    """
    from quodeq.data.fs.report_parser.runs import list_runs

    project_uuid = "proj-1"
    run_dir = tmp_path / project_uuid / "run-historical"
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "evidence" / "manifest.json").write_text("{}")
    (run_dir / "evaluation").mkdir()
    # No .pid, no scan.json — a typical historical run

    runs = list_runs(tmp_path, project_uuid)
    assert len(runs) == 1
    assert runs[0].status == "complete"


def test_list_runs_dead_pid_is_historical(tmp_path: Path) -> None:
    """A run whose .pid points to a dead process is treated as historical/complete."""
    from quodeq.data.fs.report_parser.runs import list_runs

    project_uuid = "proj-1"
    run_dir = tmp_path / project_uuid / "run-dead-pid"
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "evidence" / "manifest.json").write_text("{}")
    (run_dir / "evaluation").mkdir()
    # A PID unlikely to exist on any system
    (run_dir / ".pid").write_text("999999")

    runs = list_runs(tmp_path, project_uuid)
    assert len(runs) == 1
    assert runs[0].status == "complete"


def test_list_runs_skips_dirs_without_manifest(tmp_path: Path) -> None:
    """A directory without evidence/manifest.json (pre-manifest abort) is not a run."""
    from quodeq.data.fs.report_parser.runs import list_runs

    project_uuid = "proj-1"
    empty_dir = tmp_path / project_uuid / "empty"
    empty_dir.mkdir(parents=True)

    runs = list_runs(tmp_path, project_uuid)
    assert runs == []


def test_list_runs_mixes_historical_and_in_progress(tmp_path: Path) -> None:
    """Historical runs stay visible; only live-PID runs get the in_progress flag."""
    from quodeq.data.fs.report_parser.runs import list_runs

    project_uuid = "proj-2"
    project_dir = tmp_path / project_uuid

    # Historical run (no .pid)
    old_dir = project_dir / "run-historical"
    (old_dir / "evidence").mkdir(parents=True)
    (old_dir / "evidence" / "manifest.json").write_text("{}")
    (old_dir / "evaluation").mkdir()

    # Live run (.pid with our PID)
    live_dir = project_dir / "run-live"
    (live_dir / "evidence").mkdir(parents=True)
    (live_dir / "evidence" / "manifest.json").write_text("{}")
    (live_dir / "evaluation").mkdir()
    (live_dir / ".pid").write_text(str(os.getpid()))

    # Empty / pre-manifest dir — should be skipped
    stray = project_dir / "stray"
    stray.mkdir(parents=True)

    runs = list_runs(tmp_path, project_uuid)
    by_id = {r.run_id: r.status for r in runs}
    assert by_id == {
        "run-historical": "complete",
        "run-live": "in_progress",
    }
