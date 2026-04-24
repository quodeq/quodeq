"""RunLifecycleContext — unifies status + heartbeat + signal handlers + atexit + exception mapping.

Intended usage:

    with RunLifecycleContext(run_dir, job_id, dimensions) as ctx:
        # Pipeline writes status.json at pending → running automatically.
        do_work()
        ctx.transition_to_finalizing()
        finalize()
    # On normal exit: status.json state=done.
    # On exception:   state=failed (+ exit_reason).
    # On signal:      state=cancelled (+ exit_reason=signal_*).
    # On atexit:      state=cancelled (+ exit_reason=atexit_unfinalized) if still non-terminal.

Signal handlers are restored on __exit__. atexit hook self-deregisters on clean transition out.
"""
from __future__ import annotations

import atexit
import logging
import signal
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Any

from quodeq.shared import cancellation
from quodeq.shared.run_heartbeat import HeartbeatThread
from quodeq.shared.run_status import (
    RunState,
    TERMINAL_STATES,
    read_status,
    validate_transition,
    write_status,
)

_logger = logging.getLogger(__name__)

_SIGNALS_TO_HANDLE = (signal.SIGINT, signal.SIGTERM)
# SIGHUP is POSIX-only. Included conditionally below.
if hasattr(signal, "SIGHUP"):
    _SIGNALS_TO_HANDLE = _SIGNALS_TO_HANDLE + (signal.SIGHUP,)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RunLifecycleContext:
    """Context manager bundling lifecycle state + heartbeat + signals + atexit."""

    def __init__(
        self,
        run_dir: Path,
        job_id: str,
        dimensions: list[str],
        *,
        heartbeat_interval: float = 5.0,
    ) -> None:
        self._run_dir = run_dir
        self._job_id = job_id
        self._dimensions = list(dimensions)
        self._started_at = _now_iso()
        self._current_state = RunState.PENDING
        self._phase: str | None = None
        self._current_dimension: str | None = None
        self._heartbeat = HeartbeatThread(run_dir, interval=heartbeat_interval)
        self._previous_handlers: dict[int, Any] = {}
        self._atexit_registered = False

    # ---- Context protocol --------------------------------------------------

    def __enter__(self) -> "RunLifecycleContext":
        cancellation.reset()
        self._write(RunState.PENDING)
        self._install_signal_handlers()
        atexit.register(self._finalize_on_atexit)
        self._atexit_registered = True
        self._transition(RunState.RUNNING)
        self._heartbeat.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        self._heartbeat.stop()
        if exc_type is None:
            # No exception — pipeline is expected to have transitioned to finalizing.
            if self._current_state not in TERMINAL_STATES:
                if self._current_state != RunState.FINALIZING:
                    # Caller didn't explicitly call transition_to_finalizing(); do it now.
                    self._transition(RunState.FINALIZING)
                self._transition(RunState.DONE)
        elif issubclass(exc_type, SystemExit):
            # SystemExit raised by our signal handler; state already written there.
            if self._current_state not in TERMINAL_STATES:
                self._transition(RunState.CANCELLED, exit_reason="systemexit")
        else:
            # Any other exception → failed.
            if self._current_state not in TERMINAL_STATES:
                exc_name = exc_type.__name__ if exc_type else "UnknownError"
                self._transition(RunState.FAILED, exit_reason=f"exception: {exc_name}")
        self._restore_signal_handlers()
        self._deregister_atexit()
        return False  # never swallow exceptions

    # ---- Transition API ----------------------------------------------------

    def transition_to_finalizing(self) -> None:
        self._transition(RunState.FINALIZING)

    def set_phase(self, phase: str | None, current_dimension: str | None = None) -> None:
        self._phase = phase
        self._current_dimension = current_dimension
        self._write(self._current_state)

    # ---- Internals ---------------------------------------------------------

    def _transition(self, new_state: RunState, *, exit_reason: str | None = None) -> None:
        validate_transition(self._current_state, new_state)
        self._current_state = new_state
        self._write(new_state, exit_reason=exit_reason)

    def _write(self, state: RunState, *, exit_reason: str | None = None) -> None:
        write_status(
            self._run_dir,
            state=state,
            job_id=self._job_id,
            started_at=self._started_at,
            dimensions=self._dimensions,
            phase=self._phase,
            current_dimension=self._current_dimension,
            exit_reason=exit_reason,
        )

    def _install_signal_handlers(self) -> None:
        def _handle(signum: int, frame: Any) -> None:
            try:
                name = signal.Signals(signum).name
            except ValueError:
                name = f"signal_{signum}"
            # Signal worker threads (subagent pool, AI CLI subprocess monitors)
            # to stop waiting on long-running operations and terminate promptly.
            cancellation.request_cancel()
            # Avoid using the transition-validating path — we may be mid-state.
            self._heartbeat.stop()
            write_status(
                self._run_dir,
                state=RunState.CANCELLED,
                job_id=self._job_id,
                started_at=self._started_at,
                dimensions=self._dimensions,
                phase=self._phase,
                current_dimension=self._current_dimension,
                exit_reason=f"signal_{name}",
            )
            self._current_state = RunState.CANCELLED
            raise SystemExit(128 + signum)

        for sig in _SIGNALS_TO_HANDLE:
            try:
                self._previous_handlers[sig] = signal.getsignal(sig)
                signal.signal(sig, _handle)
            except (OSError, ValueError):
                # Can fail in non-main threads; tests may run under such a case.
                pass

    def _restore_signal_handlers(self) -> None:
        for sig, prev in self._previous_handlers.items():
            try:
                signal.signal(sig, prev)
            except (OSError, ValueError):
                pass
        self._previous_handlers.clear()

    def _finalize_on_atexit(self) -> None:
        current = read_status(self._run_dir)
        if current is None:
            return
        state_str = current.get("state")
        if state_str in {s.value for s in TERMINAL_STATES}:
            return
        # We exited without a terminal state — write cancelled.
        self._heartbeat.stop()
        write_status(
            self._run_dir,
            state=RunState.CANCELLED,
            job_id=self._job_id,
            started_at=self._started_at,
            dimensions=self._dimensions,
            phase=self._phase,
            current_dimension=self._current_dimension,
            exit_reason="atexit_unfinalized",
        )

    def _deregister_atexit(self) -> None:
        if not self._atexit_registered:
            return
        try:
            atexit.unregister(self._finalize_on_atexit)
        except Exception:
            pass
        self._atexit_registered = False
