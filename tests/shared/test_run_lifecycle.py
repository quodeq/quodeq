from __future__ import annotations

import signal
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.shared.run_status import RunState, read_status
from quodeq.shared.run_lifecycle import RunLifecycleContext

# os.kill(pid, SIGTERM) on Windows calls TerminateProcess directly — it does
# not invoke Python signal handlers, so any test that signals its own process
# kills the pytest runner outright. The signal-handler logic is POSIX-only
# behaviour anyway; on Windows the runner relies on console events / atexit.
_POSIX_SIGNALS = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only: os.kill(pid, SIGTERM) terminates the process on Windows without invoking Python handlers",
)


def _ctx(tmp_path: Path) -> RunLifecycleContext:
    return RunLifecycleContext(
        run_dir=tmp_path,
        job_id="ext-test",
        dimensions=["security"],
    )


def test_context_writes_pending_then_running(tmp_path: Path) -> None:
    with _ctx(tmp_path) as ctx:
        status = read_status(tmp_path)
        assert status["state"] == "running"  # transition happened on __enter__
        ctx.transition_to_finalizing()
        assert read_status(tmp_path)["state"] == "finalizing"
    final = read_status(tmp_path)
    assert final["state"] == "done"
    assert final["finalized_at"] is not None


def test_exception_writes_failed(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        with _ctx(tmp_path):
            raise ValueError("boom")
    status = read_status(tmp_path)
    assert status["state"] == "failed"
    assert status["exit_reason"] == "exception: ValueError"


def test_systemexit_treated_as_cancelled(tmp_path: Path) -> None:
    """SystemExit from a signal handler must produce state=cancelled."""
    with pytest.raises(SystemExit):
        with _ctx(tmp_path):
            raise SystemExit(130)
    status = read_status(tmp_path)
    assert status["state"] == "cancelled"


@_POSIX_SIGNALS
def test_signal_handler_writes_cancelled(tmp_path: Path) -> None:
    """Sending SIGTERM while in context writes cancelled with signal exit_reason."""
    import os, time

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


def test_context_enter_resets_stale_cancel_event(tmp_path: Path) -> None:
    """Entering a new lifecycle context must clear leftover cancel state
    so a second run in the same process does not see cancellation from the first."""
    from quodeq.shared import cancellation

    cancellation.request_cancel()
    assert cancellation.is_cancelled() is True
    try:
        with _ctx(tmp_path):
            assert cancellation.is_cancelled() is False
    finally:
        cancellation.reset()


def test_restores_previous_signal_handlers(tmp_path: Path) -> None:
    """After __exit__, signal handlers revert to what they were before __enter__."""
    sentinel = signal.getsignal(signal.SIGINT)
    with _ctx(tmp_path):
        assert signal.getsignal(signal.SIGINT) is not sentinel  # our handler is installed
    assert signal.getsignal(signal.SIGINT) is sentinel


def test_heartbeat_is_touched_during_context(tmp_path: Path) -> None:
    with _ctx(tmp_path):
        import time; time.sleep(0.1)  # allow heartbeat thread to run at least once
        assert (tmp_path / ".heartbeat").exists()


def test_transition_methods(tmp_path: Path) -> None:
    """The context exposes explicit transition methods so callers don't touch status files directly."""
    with _ctx(tmp_path) as ctx:
        ctx.set_phase("analyzing", current_dimension="security")
        status = read_status(tmp_path)
        assert status["phase"] == "analyzing"
        assert status["current_dimension"] == "security"
