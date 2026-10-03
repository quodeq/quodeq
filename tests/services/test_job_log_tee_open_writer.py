"""TeeContext.open_writer seam: an injected writer factory backs the opened
writer, and the existing RunLogWriter patch still bites when nothing is
injected. Split from test_jobs_run_log.py to stay under the file-size cap
(also carries test_drain_pre_marker_buffer_survives_broken_pipe, moved here
since it's the file's other drain_pre_marker_buffer/TeeContext user)."""
from __future__ import annotations

from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from quodeq.services._job_log_tee import TeeContext, drain_pre_marker_buffer


def test_drain_pre_marker_buffer_survives_broken_pipe(tmp_path: Path) -> None:
    """A BrokenPipeError out of writer.write() during the final drain must be
    logged and swallowed, not raised -- mirrors the (IOError, BrokenPipeError)
    handling in _read_and_tee_loop two functions up in _job_log_tee.py."""
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
        pre_marker_buffer={job_id: deque(["buffered-1", "buffered-2"])},
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
    assert ctx.pre_marker_buffer[job_id] == deque()


def test_injected_open_writer_is_used_instead_of_run_log_writer(tmp_path: Path) -> None:
    """TeeContext.open_writer seam: a fake writer factory must back the
    opened writer, proving the real RunLogWriter was never constructed."""
    run_dir = tmp_path / "proj-fake" / "run-fake"
    run_dir.mkdir(parents=True)

    store = MagicMock()
    store.get.return_value = SimpleNamespace(output_project="proj-fake", output_run_id="run-fake")

    opened: list[Path] = []
    written: list[str] = []

    class _FakeWriter:
        def __init__(self, path: Path) -> None:
            opened.append(path)

        def write(self, line: str) -> None:
            written.append(line)

    ctx = TeeContext(
        store=store,
        reports_root=tmp_path,
        run_log_writers={},
        pre_marker_buffer={"job-fake": deque(["buffered-line"])},
        log=MagicMock(),
        flush_batch=MagicMock(),
        open_writer=_FakeWriter,
    )

    with patch("quodeq.services._job_log_tee.RunLogWriter", side_effect=AssertionError("must not build RunLogWriter")):
        drain_pre_marker_buffer("job-fake", ctx)

    assert opened == [run_dir]
    assert written == ["buffered-line"]
    assert isinstance(ctx.run_log_writers["job-fake"], _FakeWriter)


def test_default_open_writer_still_resolves_to_the_patched_run_log_writer(tmp_path: Path) -> None:
    """Existing patch target keeps biting: no open_writer injected -> falls
    back to this module's RunLogWriter, resolved at call time."""
    run_dir = tmp_path / "proj-real" / "run-real"
    run_dir.mkdir(parents=True)

    store = MagicMock()
    store.get.return_value = SimpleNamespace(output_project="proj-real", output_run_id="run-real")

    ctx = TeeContext(
        store=store,
        reports_root=tmp_path,
        run_log_writers={},
        pre_marker_buffer={"job-real": deque(["buffered-line"])},
        log=MagicMock(),
        flush_batch=MagicMock(),
    )

    with patch("quodeq.services._job_log_tee.RunLogWriter") as MockWriter:
        drain_pre_marker_buffer("job-real", ctx)

    MockWriter.assert_called_once_with(run_dir)
