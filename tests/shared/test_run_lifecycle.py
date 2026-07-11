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


@_POSIX_SIGNALS
def test_signal_handlers_installed_before_first_status_write(tmp_path: Path) -> None:
    """Handlers must be live before status.json first appears on disk.

    External cancellers (dashboard, e2e tests) treat the existence of
    status.json as "safe to SIGTERM". If __enter__ wrote the file before
    installing handlers, a signal landing in that gap would hit the default
    handler and kill the run with the status stuck at pending.
    """
    from quodeq.shared import run_lifecycle as rl

    order: list[str] = []
    real_signal = signal.signal
    real_write = rl.write_status

    def recording_signal(sig, handler):
        order.append("install")
        return real_signal(sig, handler)

    def recording_write(*args, **kwargs):
        order.append("write")
        return real_write(*args, **kwargs)

    with patch.object(rl.signal, "signal", side_effect=recording_signal), \
         patch.object(rl, "write_status", side_effect=recording_write):
        with _ctx(tmp_path):
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


def test_lifecycle_seeds_dimensions_pending(tmp_path: Path) -> None:
    """RunLifecycleContext seeds dimensions.json with PENDING entries on enter."""
    from quodeq.shared.dimensions_state import read_dimensions

    with RunLifecycleContext(run_dir=tmp_path, job_id="j1", dimensions=["a", "b"]):
        data = read_dimensions(tmp_path)
        assert data["dimensions"]["a"]["state"] == "pending"
        assert data["dimensions"]["b"]["state"] == "pending"


def test_set_exit_reason_persists_into_status_on_done(tmp_path: Path) -> None:
    """set_exit_reason('deadline') called during the run → status.json
    after a clean exit has state=done AND exit_reason='deadline'."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with RunLifecycleContext(run_dir, job_id="ext-test", dimensions=["flex"]) as ctx:
        ctx.set_exit_reason("deadline")
        ctx.transition_to_finalizing()

    status = read_status(run_dir)
    assert status is not None
    assert status["state"] == "done"
    assert status["exit_reason"] == "deadline"


def test_no_set_exit_reason_yields_null_on_done(tmp_path: Path) -> None:
    """Without set_exit_reason, a clean run still completes with
    exit_reason=null (preserving today's contract for completed runs)."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with RunLifecycleContext(run_dir, job_id="ext-test", dimensions=["flex"]) as ctx:
        ctx.transition_to_finalizing()

    status = read_status(run_dir)
    assert status is not None
    assert status["state"] == "done"
    assert status.get("exit_reason") in (None, "")


def test_exception_exit_reason_overrides_user_set(tmp_path: Path) -> None:
    """An uncaught exception's exit_reason takes precedence over any
    previously-set 'normal' reason — failures aren't mislabeled."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with pytest.raises(ValueError):
        with RunLifecycleContext(run_dir, job_id="ext-test", dimensions=["flex"]) as ctx:
            ctx.set_exit_reason("deadline")
            raise ValueError("boom")

    status = read_status(run_dir)
    assert status is not None
    assert status["state"] == "failed"
    assert "exception" in status["exit_reason"]


def test_breaker_exit_writes_failed_with_reason(tmp_path: Path) -> None:
    """CircuitBreakerError raised from inside the lifecycle context maps
    to state=failed with exit_reason=failure_streak."""
    from quodeq.analysis.cache._failure_streak import CircuitBreakerError

    raised = False
    try:
        with RunLifecycleContext(run_dir=tmp_path, job_id="j1", dimensions=["a"]):
            raise CircuitBreakerError("circuit_breaker")
    except CircuitBreakerError:
        raised = True

    assert raised
    status = read_status(tmp_path)
    assert status is not None
    assert status["state"] == "failed"
    assert status["exit_reason"] == "failure_streak"


def test_lifecycle_context_threads_provider_to_status(tmp_path: Path) -> None:
    """ai_provider and ai_model passed to RunLifecycleContext must land in status.json."""
    with RunLifecycleContext(
        run_dir=tmp_path,
        job_id="ext-1",
        dimensions=["maintainability"],
        ai_provider="ollama",
        ai_model="gemma4:26b-mlx",
    ):
        pass
    data = read_status(tmp_path)
    assert data["ai_provider"] == "ollama"
    assert data["ai_model"] == "gemma4:26b-mlx"
