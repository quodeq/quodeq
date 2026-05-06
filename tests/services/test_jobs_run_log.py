from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quodeq.services.jobs import JobManager, STATUS_RUNNING
from quodeq.services._job_model import Job, _CONSUME_BATCH_SIZE


def _make_job(job_id: str) -> Job:
    return Job(
        job_id=job_id,
        status=STATUS_RUNNING,
        command=["x"],
        started_at="2026-04-20T00:00:00+00:00",
        ended_at=None,
        exit_code=None,
    )


def test_consume_stream_tees_to_run_log(tmp_path: Path) -> None:
    """Once the report_path marker arrives, subsequent lines land in run.log."""
    project = "proj-uuid"
    run_id = "run-A"
    run_dir = tmp_path / project / run_id
    run_dir.mkdir(parents=True)

    jm = JobManager(reports_root=tmp_path)
    jm._store.put(_make_job("job-1"))

    marker = json.dumps({"_cc": "report_path", "project": project, "runId": run_id})
    stream = iter([
        "pre-marker line\n",
        marker + "\n",
        "post-marker line\n",
    ])
    jm._consume_stream("job-1", stream)

    contents = (run_dir / "run.log").read_text()
    # Both pre-marker (buffered) and post-marker lines must appear, in order.
    assert "pre-marker line" in contents
    assert "post-marker line" in contents
    assert contents.index("pre-marker line") < contents.index("post-marker line")


def test_consume_stream_no_run_dir_silent(tmp_path: Path) -> None:
    """If no report_path marker ever arrives, consume_stream completes without error."""
    jm = JobManager(reports_root=tmp_path)
    jm._store.put(_make_job("job-2"))
    jm._consume_stream("job-2", iter(["line-1\n", "line-2\n"]))
    # No run.log anywhere — nothing to assert beyond "did not raise".


def test_consume_stream_filters_cc_markers_from_run_log(tmp_path: Path) -> None:
    """_cc JSON markers are structured IPC — they must NOT leak into run.log.

    Without filtering, the xterm pane in the dashboard shows raw JSON lines
    mixed into the terminal output (e.g. `{"_cc": "analyzing", "dimension": "security"}`).
    The marker is still applied to the job's phase/current_dimension state via
    _append_log; only the visible terminal output is cleaned up.
    """
    project = "proj-uuid"
    run_id = "run-CC"
    run_dir = tmp_path / project / run_id
    run_dir.mkdir(parents=True)

    jm = JobManager(reports_root=tmp_path)
    jm._store.put(_make_job("job-cc"))

    report_marker = json.dumps({"_cc": "report_path", "project": project, "runId": run_id})
    analyzing_marker = json.dumps({"_cc": "analyzing", "dimension": "security"})
    scoring_marker = json.dumps({"_cc": "scoring", "dimension": "reliability"})
    stream = iter([
        report_marker + "\n",
        "Starting evaluation...\n",
        analyzing_marker + "\n",
        "→ [1/3] Analyzing security\n",
        scoring_marker + "\n",
        "Scoring complete\n",
    ])
    jm._consume_stream("job-cc", stream)

    # RunLogWriter writes UTF-8; on Windows read_text() defaults to cp1252
    # and mojibakes the unicode arrow. Force utf-8.
    contents = (run_dir / "run.log").read_text(encoding="utf-8")
    # Human-readable lines survive.
    assert "Starting evaluation..." in contents
    assert "\u2192 [1/3] Analyzing security" in contents
    assert "Scoring complete" in contents
    # Marker JSON lines are filtered out — no raw {"_cc": ...} in the terminal.
    assert '"_cc"' not in contents
    assert "report_path" not in contents
    assert "analyzing" not in contents.lower() or "analyzing security" in contents.lower()


def test_consume_stream_marker_still_updates_job_state(tmp_path: Path) -> None:
    """Filtering markers from run.log must NOT break their IPC role.

    _append_log still parses and applies the marker to the job (phase,
    current_dimension, output_project, output_run_id). Only the literal
    JSON line is skipped from the run.log tee.
    """
    project = "proj-state"
    run_id = "run-state"
    run_dir = tmp_path / project / run_id
    run_dir.mkdir(parents=True)

    jm = JobManager(reports_root=tmp_path)
    jm._store.put(_make_job("job-state"))

    report_marker = json.dumps({"_cc": "report_path", "project": project, "runId": run_id})
    analyzing_marker = json.dumps({"_cc": "analyzing", "dimension": "security"})
    jm._consume_stream("job-state", iter([report_marker + "\n", analyzing_marker + "\n"]))

    job = jm._store.get("job-state")
    assert job.output_project == project
    assert job.output_run_id == run_id
    assert job.phase == "analyzing"
    assert job.current_dimension == "security"


# ---------------------------------------------------------------------------
# Fix 1: Production wiring — provider instantiated with reports_root
# ---------------------------------------------------------------------------

def test_provider_wires_reports_root_to_job_manager(tmp_path: Path) -> None:
    """FilesystemActionProvider passes reports_root to JobManager at construction."""
    from quodeq.services.filesystem import FilesystemActionProvider

    provider = FilesystemActionProvider(reports_root=tmp_path)
    assert provider._jobs._reports_root == tmp_path


def test_set_reports_root_updates_job_manager(tmp_path: Path) -> None:
    """JobManager.set_reports_root updates _reports_root for subsequent tee calls."""
    jm = JobManager()
    assert jm._reports_root is None
    jm.set_reports_root(tmp_path)
    assert jm._reports_root == tmp_path

    # Verify that a stream now tees to run.log via the updated root.
    project = "proj-wire"
    run_id = "run-wire"
    run_dir = tmp_path / project / run_id
    run_dir.mkdir(parents=True)

    jm._store.put(_make_job("job-wire"))
    marker = json.dumps({"_cc": "report_path", "project": project, "runId": run_id})
    jm._consume_stream("job-wire", iter(["hello\n", marker + "\n", "world\n"]))

    contents = (run_dir / "run.log").read_text()
    assert "hello" in contents
    assert "world" in contents


# ---------------------------------------------------------------------------
# Fix 2: Batch-boundary ordering
# ---------------------------------------------------------------------------

def test_batch_boundary_all_lines_in_run_log_in_order(tmp_path: Path) -> None:
    """All 100 lines appear in run.log in order even when marker is mid-stream.

    This exercises the batch boundary: with _CONSUME_BATCH_SIZE lines flushed
    per batch, the marker may land in the middle of a batch.  The final
    _drain_pre_marker_buffer call must ensure no buffered lines are lost.
    """
    project = "proj-batch"
    run_id = "run-batch"
    run_dir = tmp_path / project / run_id
    run_dir.mkdir(parents=True)

    total = 100
    marker_pos = 50  # marker at line index 50 (0-based)
    marker = json.dumps({"_cc": "report_path", "project": project, "runId": run_id})

    lines = []
    for i in range(total):
        if i == marker_pos:
            lines.append(marker + "\n")
        else:
            lines.append(f"line-{i}\n")

    jm = JobManager(reports_root=tmp_path)
    jm._store.put(_make_job("job-batch"))
    jm._consume_stream("job-batch", iter(lines))

    contents = (run_dir / "run.log").read_text()
    log_lines = [l for l in contents.splitlines() if l.startswith("line-")]
    # All 99 data lines (not the marker) must be present.
    assert len(log_lines) == total - 1
    # Verify ordering: line numbers extracted must be monotonically increasing.
    nums = [int(l.split("-")[1]) for l in log_lines]
    assert nums == sorted(nums)
    # Lines before and after the marker must both appear.
    assert any(n < marker_pos for n in nums)
    assert any(n > marker_pos for n in nums)


# ---------------------------------------------------------------------------
# Fix 3: Resource cleanup on unexpected exceptions
# ---------------------------------------------------------------------------

def test_consume_stream_cleans_up_on_unexpected_exception(tmp_path: Path) -> None:
    """Writer and buffer are cleaned up even when the stream raises an unexpected error."""
    project = "proj-exc"
    run_id = "run-exc"
    run_dir = tmp_path / project / run_id
    run_dir.mkdir(parents=True)

    marker = json.dumps({"_cc": "report_path", "project": project, "runId": run_id})

    def _bad_stream():
        yield "line-1\n"
        yield marker + "\n"
        raise RuntimeError("unexpected stream error")

    jm = JobManager(reports_root=tmp_path)
    jm._store.put(_make_job("job-exc"))

    with pytest.raises(RuntimeError, match="unexpected stream error"):
        jm._consume_stream("job-exc", _bad_stream())

    # Writer and buffer must be cleaned up regardless.
    assert "job-exc" not in jm._run_log_writers
    assert "job-exc" not in jm._pre_marker_buffer
