"""Tests for list_runs() run discovery and status detection."""
import json
import os
from pathlib import Path


# ---------------------------------------------------------------------------
# #144 — _read_run_status must not raise when status.json parses to a non-dict
# ---------------------------------------------------------------------------

class TestReadRunStatusNonDict:
    def _make_run(self, tmp_path: Path, run_id: str) -> Path:
        run_dir = tmp_path / "proj" / run_id
        (run_dir / "evidence").mkdir(parents=True)
        (run_dir / "evidence" / "manifest.json").write_text("{}")
        return run_dir

    def test_list_payload_returns_complete(self, tmp_path: Path) -> None:
        from quodeq.data.fs.report_parser.runs import list_runs
        run_dir = self._make_run(tmp_path, "run-list")
        (run_dir / "status.json").write_text(json.dumps([1, 2, 3]))
        runs = list_runs(tmp_path, "proj")
        assert len(runs) == 1
        assert runs[0].status == "complete"

    def test_string_payload_returns_complete(self, tmp_path: Path) -> None:
        from quodeq.data.fs.report_parser.runs import list_runs
        run_dir = self._make_run(tmp_path, "run-string")
        (run_dir / "status.json").write_text('"cancelled"')
        runs = list_runs(tmp_path, "proj")
        assert len(runs) == 1
        assert runs[0].status == "complete"

    def test_null_payload_returns_complete(self, tmp_path: Path) -> None:
        from quodeq.data.fs.report_parser.runs import list_runs
        run_dir = self._make_run(tmp_path, "run-null")
        (run_dir / "status.json").write_text("null")
        runs = list_runs(tmp_path, "proj")
        assert len(runs) == 1
        assert runs[0].status == "complete"


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


def test_list_runs_cancelled_state_overrides_live_pid(tmp_path: Path) -> None:
    """A run cancelled while its process is still draining shows as cancelled.

    The cancel path writes ``state: cancelled`` to status.json immediately, but
    the subprocess keeps running for a few seconds while it reaps its subagents.
    During that window a live PID must NOT override the explicit terminal state,
    or the History table shows a cancelled run as "running".
    """
    from quodeq.data.fs.report_parser.runs import list_runs

    project_uuid = "proj-cancel"
    run_dir = tmp_path / project_uuid / "run-draining"
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "evidence" / "manifest.json").write_text("{}")
    # status.json already flipped to cancelled by the cancel path...
    (run_dir / "status.json").write_text(json.dumps({"state": "cancelled"}))
    # ...but the process is still alive (our own PID passes the liveness probe).
    (run_dir / ".pid").write_text(str(os.getpid()))

    runs = list_runs(tmp_path, project_uuid)
    assert len(runs) == 1
    assert runs[0].status == "cancelled"


def test_list_runs_failed_state_overrides_live_pid(tmp_path: Path) -> None:
    """A failed terminal state also wins over a lingering live PID."""
    from quodeq.data.fs.report_parser.runs import list_runs

    project_uuid = "proj-failed"
    run_dir = tmp_path / project_uuid / "run-failing"
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "evidence" / "manifest.json").write_text("{}")
    (run_dir / "status.json").write_text(json.dumps({"state": "failed"}))
    (run_dir / ".pid").write_text(str(os.getpid()))

    runs = list_runs(tmp_path, project_uuid)
    assert len(runs) == 1
    assert runs[0].status == "failed"


def test_list_runs_running_state_with_live_pid_stays_in_progress(tmp_path: Path) -> None:
    """A genuinely running run (non-terminal state + live PID) stays in_progress.

    Guards the fix from over-reaching: only *terminal* states short-circuit the
    live-PID check.
    """
    from quodeq.data.fs.report_parser.runs import list_runs

    project_uuid = "proj-running"
    run_dir = tmp_path / project_uuid / "run-alive"
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "evidence" / "manifest.json").write_text("{}")
    (run_dir / "status.json").write_text(json.dumps({"state": "running"}))
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


def test_list_runs_accepts_status_json_without_manifest(tmp_path: Path) -> None:
    """A run with status.json but no manifest is a real run.

    Runs started without a prescan never write evidence/manifest.json, and a
    failed manifest write is swallowed. The SQLite index (History) accepts any
    run with a status.json, so the Overview's enumerator skipping the same run
    made the two views disagree: visible in History, "No evaluations yet" in
    the Overview (a 404 when the finished run was the pinned selection).
    """
    import json as _json
    from quodeq.data.fs.report_parser.runs import list_runs

    project_uuid = "proj-3"
    run_dir = tmp_path / project_uuid / "run-nomanifest"
    run_dir.mkdir(parents=True)
    (run_dir / "status.json").write_text(
        _json.dumps({"schema_version": 1, "state": "done", "job_id": "ext-x",
                     "started_at": "2026-07-01T00:00:00+00:00", "dimensions": []}),
        encoding="utf-8",
    )

    runs = list_runs(tmp_path, project_uuid)
    assert [r.run_id for r in runs] == ["run-nomanifest"]
    assert runs[0].status == "complete"
