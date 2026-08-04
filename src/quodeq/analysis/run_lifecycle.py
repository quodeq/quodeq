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
from quodeq.data.fs.run_status_store import (
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
        ai_provider: str | None = None,
        ai_model: str | None = None,
    ) -> None:
        self._run_dir = run_dir
        self._job_id = job_id
        self._dimensions = list(dimensions)
        self._started_at = _now_iso()
        self._current_state = RunState.PENDING
        self._phase: str | None = None
        self._current_dimension: str | None = None
        self._deadline_at: str | None = None
        self._time_limit_s: int | None = None
        self._ai_provider = ai_provider
        self._ai_model = ai_model
        self._heartbeat = HeartbeatThread(run_dir, interval=heartbeat_interval)
        self._resources = ResourceSampler()
        self._previous_handlers: dict[int, Any] = {}
        self._atexit_registered = False
        self._pending_exit_reason: str | None = None

    # ---- Context protocol --------------------------------------------------

    def __enter__(self) -> "RunLifecycleContext":
        cancellation.reset()
        # Handlers and the atexit fallback must be in place before status.json
        # first appears on disk: external cancellers (dashboard, e2e tests)
        # treat its existence as "safe to signal", so a SIGTERM landing in the
        # gap would hit the default handler and kill the run with the status
        # stuck at pending.
        self._install_signal_handlers()
        atexit.register(self._finalize_on_atexit)
        self._atexit_registered = True
        self._write(RunState.PENDING)
        self._seed_dimension_states()
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
                # The failure-streak breaker aborts the remaining dimensions from
                # inside the pipeline, so a truncated run reaches this clean-exit
                # path with dims still pending. Record that rather than reporting
                # a done/None status that reads exactly like a full run — the
                # skipped dims are dropped from the run average, and they tend to
                # be the ones late in the order, not a random sample.
                skipped = self._mark_unfinished_dims_incomplete("not_reached")
                self._transition(
                    RunState.DONE,
                    exit_reason=self._pending_exit_reason
                    or ("incomplete_dimensions" if skipped else None),
                )
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
                self._transition(RunState.DONE, exit_reason=self._pending_exit_reason)
        elif self._is_circuit_breaker_error(exc_type):
            # Circuit breaker tripped — auto-protection, not user cancel.
            # Distinct exit_reason makes the History entry distinguishable
            # from regular failures so the UI can surface it differently.
            if self._current_state not in TERMINAL_STATES:
                self._transition(RunState.FAILED, exit_reason="failure_streak")
        elif self._is_named_error(exc_type, "FatalProviderError"):
            # Provider reported an unrecoverable condition (quota exhausted,
            # auth failure, out of credits). Distinct exit_reason so the
            # History entry says why instead of a generic exception.
            if self._current_state not in TERMINAL_STATES:
                self._transition(RunState.FAILED, exit_reason="provider_fatal")
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

    def set_time_limit(self, seconds: int | None) -> None:
        """Record the run budget in seconds (0 = explicitly unlimited).

        Persisted in status.json so index-served snapshots (external runs,
        dashboard runs after a server restart) can surface the budget the
        run was actually started with.
        """
        self._time_limit_s = seconds
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
            ai_provider=self._ai_provider,
            ai_model=self._ai_model,
            time_limit_s=self._time_limit_s,
        )

    def _seed_dimension_states(self) -> None:
        """Initialise dimensions.json with one PENDING entry per dim."""
        from quodeq.data.fs.dimensions_state_store import DimState, write_dim_state
        for dim in self._dimensions:
            try:
                write_dim_state(self._run_dir, dim, DimState.PENDING)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("failed to seed dim state for %s: %s", dim, exc)

    @staticmethod
    def _is_named_error(exc_type: type[BaseException] | None, name: str) -> bool:
        """Detect an analysis-layer error class without a hard import dependency.

        Lifecycle is a shared/low-level module; importing from analysis
        would invert the dependency graph. Class-name match is enough since
        we control both ends.
        """
        if exc_type is None:
            return False
        return any(cls.__name__ == name for cls in exc_type.__mro__)

    @staticmethod
    def _is_circuit_breaker_error(exc_type: type[BaseException] | None) -> bool:
        return RunLifecycleContext._is_named_error(exc_type, "CircuitBreakerError")

    def _deadline_has_passed(self) -> bool:
        """True when the run's own deadline is set and already behind us."""
        if not self._deadline_at:
            return False
        try:
            deadline = datetime.fromisoformat(self._deadline_at)
        except (TypeError, ValueError):
            return False
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= deadline

    def _mark_unfinished_dims_incomplete(self, reason: str) -> int:
        """Flip non-terminal dims to INCOMPLETE and return how many were flipped.

        Covers ``pending`` as well as ``running``. A dimension the run never
        got to is just as unfinished as one interrupted mid-flight, and the
        state machine allows PENDING -> INCOMPLETE precisely for this. Leaving
        them at ``pending`` made a truncated run indistinguishable from a
        complete one: the scored dimensions were averaged into a run grade
        with no record that the rest never ran.
        """
        from quodeq.data.fs.dimensions_state_store import (  # noqa: PLC0415 — signal path
            DimState,
            read_dimensions,
            write_dim_state,
        )
        try:
            entries = read_dimensions(self._run_dir).get("dimensions", {})
        except Exception:  # noqa: BLE001 — a failing flip must not mask the exit
            return 0
        flipped = 0
        for dim, entry in entries.items():
            if isinstance(entry, dict) and entry.get("state") in {"running", "pending"}:
                try:
                    write_dim_state(self._run_dir, dim, DimState.INCOMPLETE, reason=reason)
                    flipped += 1
                except Exception as exc:  # noqa: BLE001
                    _logger.warning("failed to mark dim %s incomplete: %s", dim, exc)
        return flipped

    def _install_signal_handlers(self) -> None:
        def _handle(signum: int, frame: Any) -> None:
            try:
                name = signal.Signals(signum).name
            except ValueError:
                name = f"signal_{signum}"
            # A signal landing AFTER the run's own deadline is the watchdog
            # enforcing the time budget (SIGTERM at deadline+grace), not a
            # user cancel. Label it "deadline" — the UI maps that to "time
            # limit reached", not an error — and close out running dims. The
            # state stays CANCELLED either way: salvage scoring triggers key
            # off terminal failed/cancelled and must keep firing.
            deadline_enforced = self._deadline_has_passed()
            exit_reason = "deadline" if deadline_enforced else f"signal_{name}"
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
                exit_reason=exit_reason,
                deadline_at=self._deadline_at,
                ai_provider=self._ai_provider,
                ai_model=self._ai_model,
                time_limit_s=self._time_limit_s,
            )
            self._current_state = RunState.CANCELLED
            # Close out every unfinished dim, not just on the deadline path: a
            # plain cancel left the in-flight dimension stuck at 'running' and
            # the untouched ones at 'pending' for the life of the run dir.
            self._mark_unfinished_dims_incomplete(
                "time_limit" if deadline_enforced else "cancelled")
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
            ai_provider=self._ai_provider,
            ai_model=self._ai_model,
            time_limit_s=self._time_limit_s,
        )

    def _deregister_atexit(self) -> None:
        if not self._atexit_registered:
            return
        try:
            atexit.unregister(self._finalize_on_atexit)
        except Exception:
            pass
        self._atexit_registered = False
