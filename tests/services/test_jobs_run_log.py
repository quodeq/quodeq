from __future__ import annotations

import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from quodeq.services.jobs import JobManager, STATUS_RUNNING
from quodeq.services._job_log_tee import TeeContext, _iter_line_batches, drain_pre_marker_buffer
from quodeq.services._job_model import Job


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

    This exercises the batch boundary: lines are flushed in per-read batches,
    so the marker may land in the middle of a batch.  The final
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


# ---------------------------------------------------------------------------
# Per-read batching (finding 5208)
# ---------------------------------------------------------------------------

def _pipe_stream(payload: bytes) -> io.TextIOWrapper:
    """A text stream over a real pipe that already holds *payload*, writer closed.

    Iterables and StringIO cannot show batching: only a pipe-backed
    TextIOWrapper has the byte buffer consume_stream reads per burst.
    """
    read_fd, write_fd = os.pipe()
    os.write(write_fd, payload)
    os.close(write_fd)
    return io.TextIOWrapper(io.open(read_fd, "rb"), encoding="utf-8")


def _spy_flushes(jm: JobManager) -> list[list[str]]:
    flushes: list[list[str]] = []
    real_flush = jm._flush_batch

    def _spy(job_id: str, batch: list[str]) -> bool:
        flushes.append(list(batch))
        return real_flush(job_id, batch)

    jm._flush_batch = _spy
    return flushes


def test_lines_from_one_pipe_read_reach_the_job_in_one_flush(tmp_path: Path) -> None:
    """A burst already sitting in the pipe is flushed as one batch, not per line."""
    lines = [f"line-{i}" for i in range(20)]
    stream = _pipe_stream("".join(f"{line}\n" for line in lines).encode())
    jm = JobManager(reports_root=tmp_path)
    jm._store.put(_make_job("job-pipe"))
    flushes = _spy_flushes(jm)

    with stream:
        jm._consume_stream("job-pipe", stream)

    assert flushes == [lines]
    assert list(jm._store.get("job-pipe").logs) == lines


def test_pipe_reader_keeps_partial_line_and_translates_crlf(tmp_path: Path) -> None:
    """A trailing line without newline waits for EOF and is still delivered;
    CRLF is translated the way the text-mode wrapper would."""
    stream = _pipe_stream(b"first\r\nlast")
    jm = JobManager(reports_root=tmp_path)
    jm._store.put(_make_job("job-tail"))
    flushes = _spy_flushes(jm)

    with stream:
        jm._consume_stream("job-tail", stream)

    assert flushes == [["first"], ["last"]]
    assert list(jm._store.get("job-tail").logs) == ["first", "last"]


class _ChunkedStream:
    """Text-stream stand-in whose byte buffer hands back one scripted chunk
    per read1, the way a pipe returns whatever the child wrote so far."""

    encoding = "utf-8"
    errors = "strict"

    def __init__(self, chunks: list[bytes]) -> None:
        self.buffer = self
        self._chunks = list(chunks)

    def read1(self, _n: int) -> bytes:
        return self._chunks.pop(0) if self._chunks else b""


def test_long_unterminated_line_over_many_small_reads_is_delivered_whole() -> None:
    """A 5000-byte line arriving 99 bytes per read (cuts land inside
    multibyte characters) is one line once its newline arrives; the lines
    after it batch and tail as usual."""
    line = "é" * 2500
    payload = line.encode("utf-8") + b"\nsecond\nthird"
    chunks = [payload[i:i + 99] for i in range(0, len(payload), 99)]

    batches = list(_iter_line_batches(_ChunkedStream(chunks)))

    assert batches == [[line, "second"], ["third"]]


def test_crlf_split_across_reads_is_one_newline() -> None:
    """A CR at the end of one read and its LF at the start of the next
    translate to a single newline, as the text wrapper would do."""
    batches = list(_iter_line_batches(_ChunkedStream([b"first\r", b"\nlast\r\n", b"tail"])))

    assert batches == [["first", "last"], ["tail"]]


# ---------------------------------------------------------------------------
# Cluster 10: drain_pre_marker_buffer's writer.write() calls must not raise
# ---------------------------------------------------------------------------

def test_drain_pre_marker_buffer_survives_broken_pipe(tmp_path: Path) -> None:
    """A BrokenPipeError out of writer.write() during the final drain must be
    logged and swallowed, not raised -- mirrors the (IOError, BrokenPipeError)
    handling in _read_and_tee_loop two functions up in this module."""
    job_id = "job-drain"
    run_dir = tmp_path / "proj-drain" / "run-drain"
    run_dir.mkdir(parents=True)

    store = MagicMock()
    store.get.return_value = SimpleNamespace(output_project="proj-drain", output_run_id="run-drain")
    log = MagicMock()
    ctx = TeeContext(
        store=store,
        reports_root=tmp_path,
        run_log_writers={},
        pre_marker_buffer={job_id: ["buffered-1", "buffered-2"]},
        log=log,
        flush_batch=MagicMock(),
    )

    with patch("quodeq.services._job_log_tee.RunLogWriter") as MockWriter:
        writer = MockWriter.return_value
        writer.write.side_effect = BrokenPipeError("pipe closed")

        drain_pre_marker_buffer(job_id, ctx)  # must not raise

    log.warning.assert_called_once()
    assert job_id in log.warning.call_args[0][0]
    # Buffer is still cleared even though the write failed.
    assert ctx.pre_marker_buffer[job_id] == []
