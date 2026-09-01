"""RunLifecycleContext — the run's lifecycle context manager.

Composed from collaborators that each own one concern: ``_StatusWriter``
(every status.json write), ``_SignalGuard`` (install/restore of the run's
signal handlers), ``_AtexitGuard`` (the process-exit fallback hook), plus the
shared heartbeat/resource samplers. The context wires them together and keeps
the exception→state mapping in ``__exit__`` — deciding which terminal state
an exit maps to is the context manager's own job.

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

import logging
import signal  # noqa: F401 -- test_run_lifecycle.py patches `rl.signal.signal`
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Any

from quodeq.shared import cancellation
from quodeq.shared.resource_sampler import ResourceSampler
from quodeq.shared.run_heartbeat import HeartbeatThread
from quodeq.analysis._run_lifecycle_support import (
    _AtexitGuard,
    _SignalGuard,
    _finalize_run_on_atexit,
    _is_circuit_breaker_error,
    _is_named_error,
    _mark_unfinished_dims_incomplete,
    _run_signal_shutdown,
    _seed_dimension_states,
)
from quodeq.data.fs.run_status_store import (
    RunState,
    TERMINAL_STATES,
    validate_transition,
    write_status,
)

_logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _StatusWriter:
    """Owns every status.json write for one run.

    The run's identity (dir, job, start time, dimensions) is fixed at
    construction; the presentation fields (phase, deadline, ...) are plain
    mutable attributes the context updates as the run progresses. ``write``
    is the single place that knows the full status row, so the normal-path,
    signal-path, and atexit-path writes cannot drift apart.

    Kept in this module (not the sibling support module): it calls
    ``write_status`` by bare name, patched by tests at
    ``quodeq.analysis.run_lifecycle.write_status``.
    """

    def __init__(
        self,
        run_dir: Path,
        job_id: str,
        dimensions: list[str],
        *,
        ai_provider: str | None = None,
        ai_model: str | None = None,
    ) -> None:
        self.run_dir = run_dir
        self.job_id = job_id
        self.started_at = _now_iso()
        self.dimensions = list(dimensions)
        self.phase: str | None = None
        self.current_dimension: str | None = None
        self.deadline_at: str | None = None
        self.time_limit_s: int | None = None
        self.ai_provider = ai_provider
        self.ai_model = ai_model

    def write(self, state: RunState, *, exit_reason: str | None = None) -> None:
        write_status(
            self.run_dir,
            state=state,
            job_id=self.job_id,
            started_at=self.started_at,
            dimensions=self.dimensions,
            phase=self.phase,
            current_dimension=self.current_dimension,
            exit_reason=exit_reason,
            deadline_at=self.deadline_at,
            ai_provider=self.ai_provider,
            ai_model=self.ai_model,
            time_limit_s=self.time_limit_s,
        )


class RunLifecycleContext:
    """Context manager composing status writes, heartbeat, signals, and atexit."""

    def __init__(
        self,
        run_dir: Path,
        job_id: str,
        dimensions: list[str],
        *,
        heartbeat_interval: float = 5.0,
        ai_provider: str | None = None,
        ai_model: str | None = None,
    ) -> None:
        self._run_dir = run_dir
        self._dimensions = list(dimensions)
        self._current_state = RunState.PENDING
        self._status = _StatusWriter(
            run_dir, job_id, dimensions,
            ai_provider=ai_provider, ai_model=ai_model,
        )
        self._heartbeat = HeartbeatThread(run_dir, interval=heartbeat_interval)
        self._resources = ResourceSampler()
        self._signals = _SignalGuard(self._handle_signal)
        self._atexit = _AtexitGuard(self._finalize_on_atexit)
        self._pending_exit_reason: str | None = None

    # ---- Context protocol --------------------------------------------------

    def __enter__(self) -> "RunLifecycleContext":
        cancellation.reset()
        # Handlers and the atexit fallback must be in place before status.json
        # first appears on disk: external cancellers (dashboard, e2e tests)
        # treat its existence as "safe to signal", so a SIGTERM landing in the
        # gap would hit the default handler and kill the run with the status
        # stuck at pending.
        self._signals.install()
        self._atexit.register()
        self._write(RunState.PENDING)
        _seed_dimension_states(self._run_dir, self._dimensions, log=_logger)
        self._transition(RunState.RUNNING)
        self._heartbeat.start()
        self._resources.start()
        return self

    def _exit_clean(self) -> None:
        """No exception — pipeline is expected to have transitioned to finalizing."""
        if self._current_state in TERMINAL_STATES:
            return
        if self._current_state != RunState.FINALIZING:
            # Caller didn't explicitly call transition_to_finalizing(); do it now.
            self._transition(RunState.FINALIZING)
        # The failure-streak breaker aborts the remaining dimensions from
        # inside the pipeline, so a truncated run reaches this clean-exit
        # path with dims still pending. Record that rather than reporting
        # a done/None status that reads exactly like a full run — the
        # skipped dims are dropped from the run average, and they tend to
        # be the ones late in the order, not a random sample.
        skipped = _mark_unfinished_dims_incomplete(self._run_dir, "not_reached", log=_logger)
        self._transition(
            RunState.DONE,
            exit_reason=self._pending_exit_reason
            or ("incomplete_dimensions" if skipped else None),
        )

    def _exit_system_exit(self) -> None:
        """SystemExit raised by our signal handler; state already written there."""
        if self._current_state not in TERMINAL_STATES:
            self._transition(RunState.CANCELLED, exit_reason="systemexit")

    def _exit_broken_pipe(self) -> None:
        """The child's inherited stdout pipe closed under us (parent restarted
        mid-scan). The analysis itself already ran and the evidence is on
        disk, so this transitions to DONE rather than FAILED.
        """
        if self._current_state not in TERMINAL_STATES:
            if self._current_state != RunState.FINALIZING:
                self._transition(RunState.FINALIZING)
            self._transition(RunState.DONE, exit_reason=self._pending_exit_reason)

    def _exit_circuit_breaker(self) -> None:
        """Circuit breaker tripped — auto-protection, not user cancel. Distinct
        exit_reason makes the History entry distinguishable from regular failures.
        """
        if self._current_state not in TERMINAL_STATES:
            self._transition(RunState.FAILED, exit_reason="failure_streak")

    def _exit_fatal_provider(self) -> None:
        """Provider reported an unrecoverable condition (quota, auth, credits).
        Distinct exit_reason so the History entry says why instead of a
        generic exception.
        """
        if self._current_state not in TERMINAL_STATES:
            self._transition(RunState.FAILED, exit_reason="provider_fatal")

    def _exit_other_exception(self, exc_type: type[BaseException] | None) -> None:
        """Any other exception → failed."""
        if self._current_state not in TERMINAL_STATES:
            exc_name = exc_type.__name__ if exc_type else "UnknownError"
            self._transition(RunState.FAILED, exit_reason=f"exception: {exc_name}")

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        self._heartbeat.stop()
        self._resources.stop()
        if exc_type is None:
            self._exit_clean()
        elif issubclass(exc_type, SystemExit):
            self._exit_system_exit()
        elif issubclass(exc_type, BrokenPipeError):
            self._exit_broken_pipe()
        elif _is_circuit_breaker_error(exc_type):
            self._exit_circuit_breaker()
        elif _is_named_error(exc_type, "FatalProviderError"):
            self._exit_fatal_provider()
        else:
            self._exit_other_exception(exc_type)
        self._signals.restore()
        self._atexit.deregister()
        return False  # never swallow exceptions

    # ---- Transition API ----------------------------------------------------

    def transition_to_finalizing(self) -> None:
        self._transition(RunState.FINALIZING)

    def set_phase(self, phase: str | None, current_dimension: str | None = None) -> None:
        self._status.phase = phase
        self._status.current_dimension = current_dimension
        self._write(self._current_state)

    def set_deadline(self, deadline_at: str | None) -> None:
        """Record the run-level deadline. Visible immediately in status.json."""
        self._status.deadline_at = deadline_at
        self._write(self._current_state)

    def set_time_limit(self, seconds: int | None) -> None:
        """Record the run budget in seconds (0 = explicitly unlimited).

        Persisted in status.json so index-served snapshots (external runs,
        dashboard runs after a server restart) can surface the budget the
        run was actually started with.
        """
        self._status.time_limit_s = seconds
        self._write(self._current_state)

    def set_exit_reason(self, reason: str | None) -> None:
        """Record a non-failure exit reason to apply at the next terminal transition.

        Use this for clean-stop reasons that aren't exceptions, signals, or
        atexit (e.g. "deadline"). Exception/signal/atexit paths set their
        own exit_reason via ``_transition(state, exit_reason=...)`` and
        ignore any pending value here — failures must not be mislabeled.
        """
        self._pending_exit_reason = reason

    # ---- Internals ---------------------------------------------------------

    def _transition(self, new_state: RunState, *, exit_reason: str | None = None) -> None:
        validate_transition(self._current_state, new_state)
        self._current_state = new_state
        self._write(new_state, exit_reason=exit_reason)

    def _write(self, state: RunState, *, exit_reason: str | None = None) -> None:
        self._status.write(state, exit_reason=exit_reason)

    @staticmethod
    def _is_named_error(exc_type: type[BaseException] | None, name: str) -> bool:
        """Delegates to ``_run_lifecycle_support._is_named_error``; kept as a
        staticmethod because a test calls ``RunLifecycleContext._is_named_error``.
        """
        return _is_named_error(exc_type, name)

    def _handle_signal(self, signum: int, frame: Any) -> None:
        """Write CANCELLED status, close out unfinished dims, then re-raise as SystemExit."""
        _run_signal_shutdown(
            self._run_dir, self._heartbeat, self._resources, self._status,
            self._status.deadline_at, signum, log=_logger,
        )
        self._current_state = RunState.CANCELLED
        raise SystemExit(128 + signum)

    def _finalize_on_atexit(self) -> None:
        _finalize_run_on_atexit(self._run_dir, self._heartbeat, self._resources, self._status)
