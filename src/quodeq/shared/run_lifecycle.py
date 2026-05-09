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
from quodeq.shared.resource_sampler import ResourceSampler
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
        self._deadline_at: str | None = None
        self._heartbeat = HeartbeatThread(run_dir, interval=heartbeat_interval)
        self._resources = ResourceSampler()
        self._previous_handlers: dict[int, Any] = {}
        self._atexit_registered = False

    # ---- Context protocol --------------------------------------------------

    def __enter__(self) -> "RunLifecycleContext":
        cancellation.reset()
        self._write(RunState.PENDING)
        self._seed_dimension_states()
        self._install_signal_handlers()
        atexit.register(self._finalize_on_atexit)
        self._atexit_registered = True
        self._transition(RunState.RUNNING)
        self._heartbeat.start()
        self._resources.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        self._heartbeat.stop()
        self._resources.stop()
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
        elif issubclass(exc_type, BrokenPipeError):
            # BrokenPipeError fires when the child's inherited stdout pipe
            # closes — typically because our parent (the dashboard API) was
            # restarted mid-scan and the pipe it was reading is gone. The
            # analysis itself already ran (we got here because the pipeline
            # tried to print a trailing status line after the work was done);
            # the evidence is on disk. Transition to DONE rather than FAILED.
            if self._current_state not in TERMINAL_STATES:
                if self._current_state != RunState.FINALIZING:
                    self._transition(RunState.FINALIZING)
                self._transition(RunState.DONE)
        elif self._is_circuit_breaker_error(exc_type):
            # Circuit breaker tripped — auto-protection, not user cancel.
            # Distinct exit_reason makes the History entry distinguishable
            # from regular failures so the UI can surface it differently.
            if self._current_state not in TERMINAL_STATES:
                self._transition(RunState.FAILED, exit_reason="failure_streak")
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

    def set_deadline(self, deadline_at: str | None) -> None:
        """Record the run-level deadline. Visible immediately in status.json."""
        self._deadline_at = deadline_at
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
            deadline_at=self._deadline_at,
        )

    def _seed_dimension_states(self) -> None:
        """Initialise dimensions.json with one PENDING entry per dim."""
        from quodeq.shared.dimensions_state import DimState, write_dim_state
        for dim in self._dimensions:
            try:
                write_dim_state(self._run_dir, dim, DimState.PENDING)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("failed to seed dim state for %s: %s", dim, exc)

    @staticmethod
    def _is_circuit_breaker_error(exc_type: type[BaseException] | None) -> bool:
        """Detect CircuitBreakerError without a hard import dependency.

        Lifecycle is a shared/low-level module; importing from analysis.cache
        would invert the dependency graph. Class-name match is enough since
        we control both ends.
        """
        if exc_type is None:
            return False
        for cls in exc_type.__mro__:
            if cls.__name__ == "CircuitBreakerError":
                return True
        return False

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
            self._resources.stop()
            write_status(
                self._run_dir,
                state=RunState.CANCELLED,
                job_id=self._job_id,
                started_at=self._started_at,
                dimensions=self._dimensions,
                phase=self._phase,
                current_dimension=self._current_dimension,
                exit_reason=f"signal_{name}",
                deadline_at=self._deadline_at,
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
        self._resources.stop()
        write_status(
            self._run_dir,
            state=RunState.CANCELLED,
            job_id=self._job_id,
            started_at=self._started_at,
            dimensions=self._dimensions,
            phase=self._phase,
            current_dimension=self._current_dimension,
            exit_reason="atexit_unfinalized",
            deadline_at=self._deadline_at,
        )

    def _deregister_atexit(self) -> None:
        if not self._atexit_registered:
            return
        try:
            atexit.unregister(self._finalize_on_atexit)
        except Exception:
            pass
        self._atexit_registered = False
