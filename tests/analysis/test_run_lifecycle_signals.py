"""RunLifecycleContext signal handling: SIGTERM, cancel events, deadlines."""
from __future__ import annotations

import signal
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis.run_lifecycle import RunLifecycleContext
from quodeq.data.fs.run_status_store import read_status

from ._run_lifecycle_helpers import _ctx

# os.kill(pid, SIGTERM) on Windows calls TerminateProcess directly — it does
# not invoke Python signal handlers, so any test that signals its own process
# kills the pytest runner outright. The signal-handler logic is POSIX-only
# behaviour anyway; on Windows the runner relies on console events / atexit.
_POSIX_SIGNALS = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only: os.kill(pid, SIGTERM) terminates the process on Windows without invoking Python handlers",
)


@_POSIX_SIGNALS
def test_signal_handler_writes_cancelled(tmp_path: Path) -> None:
    """Sending SIGTERM while in context writes cancelled with signal exit_reason."""
    import os

    with pytest.raises(SystemExit):
        with RunLifecycleContext(run_dir=tmp_path, job_id="ext-sigterm", dimensions=[]):
            os.kill(os.getpid(), signal.SIGTERM)
    status = read_status(tmp_path)
    assert status["state"] == "cancelled"
    assert status["exit_reason"] == "signal_SIGTERM"


@_POSIX_SIGNALS
def test_signal_handler_sets_process_cancel_event(tmp_path: Path) -> None:
    """SIGTERM must set the shared cancel event so worker threads can unblock."""
    import os
    from quodeq.shared import cancellation

    cancellation.reset()
    try:
        with pytest.raises(SystemExit):
            with RunLifecycleContext(run_dir=tmp_path, job_id="ext-cancel-event", dimensions=[]):
                assert cancellation.is_cancelled() is False
                os.kill(os.getpid(), signal.SIGTERM)
        assert cancellation.is_cancelled() is True
    finally:
        cancellation.reset()


@_POSIX_SIGNALS
def test_signal_handlers_installed_before_first_status_write(tmp_path: Path) -> None:
    """Handlers must be live before status.json first appears on disk.

    External cancellers (dashboard, e2e tests) treat the existence of
    status.json as "safe to SIGTERM". If __enter__ wrote the file before
    installing handlers, a signal landing in that gap would hit the default
    handler and kill the run with the status stuck at pending.
    """
    from quodeq.analysis import run_lifecycle as rl
    from quodeq.analysis.run_lifecycle import LifecycleDeps
    from quodeq.data.fs.run_status_store import write_status as real_write

    order: list[str] = []
    real_signal = signal.signal

    def recording_signal(sig, handler):
        order.append("install")
        return real_signal(sig, handler)

    def recording_write(run_dir, status):
        order.append("write")
        return real_write(run_dir, status)

    with patch.object(rl.signal, "signal", side_effect=recording_signal):
        with RunLifecycleContext(
            run_dir=tmp_path, job_id="ext-order", dimensions=[],
            deps=LifecycleDeps(write_status=recording_write),
        ):
            pass

    assert "install" in order and "write" in order
    assert order.index("install") < order.index("write")


@_POSIX_SIGNALS
@pytest.mark.timeout(30)
def test_sigterm_mid_status_write_does_not_deadlock(tmp_path: Path) -> None:
    """A signal interrupting a status write must not deadlock the handler.

    The SIGTERM handler runs on the main thread and writes status.json
    itself. When the interrupted frame is already inside write_status
    holding the module write lock, a non-reentrant lock blocks the handler
    forever — observed as the CLI never exiting after SIGTERM under
    full-suite load.
    """
    import os

    fired = {"done": False}
    orig_replace = Path.replace

    def replace_and_signal(self, target):
        if not fired["done"] and self.name == "status.json.tmp":
            fired["done"] = True
            # Delivered to the main thread while _write_lock is held; the
            # handler runs at the next bytecode boundary, still inside it.
            os.kill(os.getpid(), signal.SIGTERM)
        return orig_replace(self, target)

    with pytest.raises(SystemExit):
        with _ctx(tmp_path) as ctx:
            with patch.object(Path, "replace", replace_and_signal):
                ctx.set_phase("analyzing")
    status = read_status(tmp_path)
    assert status["state"] == "cancelled"
    assert status["exit_reason"] == "signal_SIGTERM"


@_POSIX_SIGNALS
def test_sigterm_after_deadline_labels_time_limit_not_cancel(tmp_path: Path) -> None:
    """The watchdog enforcing the run's own time limit is not a user cancel.

    2026-07-31 incident: a 5-min-limit run drained its in-flight agent past
    deadline+grace, the JobManager watchdog SIGTERMed it, and the handler
    wrote ``cancelled/signal_SIGTERM`` — the UI showed a cancelled ERROR for
    a run that ended exactly as budgeted. When the deadline has passed, the
    signal must be recorded as ``deadline`` (UI: "time limit reached", not an
    error) and running dims must flip to INCOMPLETE instead of sticking at
    ``running`` forever. State stays ``cancelled``: the salvage-scoring
    triggers key off terminal failed/cancelled and must keep firing.
    """
    import os
    from datetime import datetime, timedelta, timezone

    from quodeq.data.fs.dimensions_state_store import DimState, read_dimensions, write_dim_state

    past = (datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat()
    with pytest.raises(SystemExit):
        with RunLifecycleContext(
            run_dir=tmp_path, job_id="ext-deadline", dimensions=["clean-architecture"],
        ) as ctx:
            ctx.set_deadline(past)
            write_dim_state(tmp_path, "clean-architecture", DimState.RUNNING)
            os.kill(os.getpid(), signal.SIGTERM)

    status = read_status(tmp_path)
    assert status["state"] == "cancelled"
    assert status["exit_reason"] == "deadline"
    entry = read_dimensions(tmp_path)["dimensions"]["clean-architecture"]
    assert entry["state"] == "incomplete"
    assert entry["reason"] == "time_limit"


@_POSIX_SIGNALS
def test_sigterm_before_deadline_stays_a_real_cancel(tmp_path: Path) -> None:
    """A SIGTERM while the deadline is still ahead is a genuine user cancel."""
    import os
    from datetime import datetime, timedelta, timezone

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    with pytest.raises(SystemExit):
        with RunLifecycleContext(
            run_dir=tmp_path, job_id="ext-user-cancel", dimensions=["security"],
        ) as ctx:
            ctx.set_deadline(future)
            os.kill(os.getpid(), signal.SIGTERM)

    status = read_status(tmp_path)
    assert status["state"] == "cancelled"
    assert status["exit_reason"] == "signal_SIGTERM"
