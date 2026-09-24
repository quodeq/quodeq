"""RunLifecycleContext — the run's lifecycle context manager.

Composed from collaborators that each own one concern: ``_StatusWriter``
(every status.json write, in ``_run_lifecycle_support.py``), ``SignalGuard``
(install/restore of the run's signal handlers), ``AtexitGuard`` (the
process-exit fallback hook), plus the shared heartbeat/resource samplers. The
context takes these collaborators via a ``LifecycleDeps`` bundle (None =
production default) and wires them together, keeping the exception→state
mapping in ``__exit__`` — deciding which terminal state an exit maps to is
the context manager's own job.

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
from pathlib import Path
from types import TracebackType
from typing import Any

from quodeq.shared import cancellation
from quodeq.analysis.errors import provider_exit_reason
from quodeq.core.run.exit_reason import ExitReason
from quodeq.shared.resource_sampler import ResourceSampler
from quodeq.shared.run_heartbeat import HeartbeatThread
from quodeq.analysis._run_lifecycle_support import (
    AtexitGuard,
    LifecycleDeps,
    SignalGuard,
    finalize_run_on_atexit,
    is_circuit_breaker_error,
    is_named_error,
    mark_unfinished_dims_incomplete,
    new_status_writer,
    run_signal_shutdown,
    seed_dimension_states,
)
from quodeq.core.run.state import RunState, TERMINAL_STATES, validate_transition
from quodeq.data.fs.run_status_store import write_status

_logger = logging.getLogger(__name__)


class RunLifecycleContext:
    """Context manager composing status writes, heartbeat, signals, and atexit."""

    def __init__(
        self,
        run_dir: Path,
        job_id: str,
        dimensions: list[str],
        *,
        ai_provider: str | None = None,
        ai_model: str | None = None,
        deps: LifecycleDeps | None = None,
    ) -> None:
        deps = deps or LifecycleDeps()
        self._run_dir = run_dir
        self._dimensions = list(dimensions)
        self._current_state = RunState.PENDING
        self._status = new_status_writer(
            run_dir, job_id, dimensions,
            ai_provider=ai_provider, ai_model=ai_model,
            write_status=deps.write_status or write_status,
        )
        self._heartbeat = (deps.heartbeat_factory or HeartbeatThread)(run_dir)
        self._resources = (deps.resources_factory or ResourceSampler)()
        self._signals = SignalGuard(self._handle_signal, log=_logger)
        self._atexit = AtexitGuard(self._finalize_on_atexit)
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
        seed_dimension_states(self._run_dir, self._dimensions, log=_logger)
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
        skipped = mark_unfinished_dims_incomplete(self._run_dir, "not_reached", log=_logger)
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
            self._transition(RunState.FAILED, exit_reason=ExitReason.FAILURE_STREAK)

    def _exit_fatal_provider(self, exc: BaseException | None) -> None:
        """Provider reported an unrecoverable condition (quota, auth, credits).
        Distinct exit_reason so the History entry says why instead of a
        generic exception.
        """
        if self._current_state not in TERMINAL_STATES:
            self._transition(RunState.FAILED, exit_reason=provider_exit_reason(getattr(exc, "reason", None)))

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
        elif is_circuit_breaker_error(exc_type):
            self._exit_circuit_breaker()
        elif is_named_error(exc_type, "FatalProviderError"):
            self._exit_fatal_provider(exc_value)
        else:
            self._exit_other_exception(exc_type)
        self._signals.restore()
        self._atexit.deregister()
        return False  # never swallow exceptions

    # ---- Transition API ----------------------------------------------------

    def transition_to_finalizing(self) -> None:
        """Mark the run as writing its report, so a crash from here reads as a finalize failure."""
        self._transition(RunState.FINALIZING)

    def set_phase(self, phase: str | None, current_dimension: str | None = None) -> None:
        """Publish the current phase and dimension to status.json for the progress UI."""
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

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        """Write CANCELLED status, close out unfinished dims, then re-raise as SystemExit."""
        run_signal_shutdown(self._heartbeat, self._resources, self._status, signum, log=_logger)
        self._current_state = RunState.CANCELLED
        raise SystemExit(128 + signum)

    def _finalize_on_atexit(self) -> None:
        finalize_run_on_atexit(self._run_dir, self._heartbeat, self._resources, self._status)
