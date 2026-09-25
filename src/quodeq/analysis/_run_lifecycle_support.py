"""Signal-guard, atexit-guard, exit-classification, and status-write helpers
for RunLifecycleContext.

Split out of ``run_lifecycle.py`` (file-size ratchet): these are
self-contained process-level primitives and pure helpers with no dependency
on the lifecycle state machine itself (the exception -> state mapping in
``__exit__``), so they compose cleanly as standalone collaborators owned by
``RunLifecycleContext``.

``_StatusWriter`` and ``LifecycleDeps`` live here too: the context takes its
collaborators (status writer, heartbeat, resource sampler) via a
``LifecycleDeps`` bundle, defaulting to the production implementations, so
tests can inject recorders/stubs without patching module attributes.

``SignalGuard`` and ``AtexitGuard`` live in ``_run_lifecycle_guards.py`` (a
further file-size split) and are re-exported here so existing imports keep
resolving.
"""
from __future__ import annotations

import signal
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from quodeq.analysis._run_lifecycle_guards import (  # noqa: F401 -- re-export
    AtexitGuard,
    SignalGuard,
    SIGNALS_TO_HANDLE as _SIGNALS_TO_HANDLE,
)
from quodeq.core.observability import LogSink
from quodeq.core.run.exit_reason import ExitReason
from quodeq.shared import cancellation
from quodeq.core.run.state import RunState, RunStatus, TERMINAL_STATES
from quodeq.data.fs.run_status_store import read_status


class _Stoppable(Protocol):
    """What ``run_signal_shutdown``/``finalize_run_on_atexit`` need from the
    heartbeat and resource-sampler collaborators: only ``stop()``."""

    def stop(self) -> None: ...


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _StatusWriter:
    """Owns every status.json write for one run.

    The run's identity (dir, job, start time, dimensions) is fixed at
    construction; the presentation fields (phase, deadline, ...) are plain
    mutable attributes the context updates as the run progresses. ``write``
    is the single place that knows the full status row, so the normal-path,
    signal-path, and atexit-path writes cannot drift apart.

    ``write_status`` is taken as a constructor keyword rather than called by
    bare name, so tests inject a recorder via ``LifecycleDeps`` instead of
    patching a module attribute. Built via ``new_status_writer`` below, not
    imported directly by name.
    """

    def __init__(
        self,
        run_dir: Path,
        job_id: str,
        dimensions: list[str],
        *,
        ai_provider: str | None = None,
        ai_model: str | None = None,
        write_status: Callable[[Path, RunStatus], None],
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
        self._write_status = write_status

    def write(self, state: RunState, *, exit_reason: str | None = None) -> None:
        status = RunStatus(
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
        self._write_status(self.run_dir, status)


def new_status_writer(
    run_dir: Path,
    job_id: str,
    dimensions: list[str],
    *,
    ai_provider: str | None = None,
    ai_model: str | None = None,
    write_status: Callable[[Path, RunStatus], None],
) -> _StatusWriter:
    """Build a ``_StatusWriter``.

    A public wrapper so ``run_lifecycle.py`` never imports the leading-
    underscore class name directly (the private-import gate treats that as
    a violation even between sibling files in the same package).
    """
    return _StatusWriter(
        run_dir, job_id, dimensions,
        ai_provider=ai_provider, ai_model=ai_model,
        write_status=write_status,
    )


@dataclass(frozen=True)
class LifecycleDeps:
    """Collaborators a RunLifecycleContext drives. None = production default.
    The support helpers still read status.json from disk (read_status, e.g.
    the atexit finalize path), so injecting write_status doesn't fully isolate it.
    """

    write_status: Callable[[Path, RunStatus], None] | None = None
    heartbeat_factory: Callable[[Path], Any] | None = None
    resources_factory: Callable[[], Any] | None = None


def _deadline_has_passed(deadline_at: str | None) -> bool:
    """True when *deadline_at* (an ISO timestamp) is set and already behind us."""
    if not deadline_at:
        return False
    try:
        deadline = datetime.fromisoformat(deadline_at)
    except (TypeError, ValueError):
        return False
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= deadline


def mark_unfinished_dims_incomplete(run_dir: Path, reason: str, *, log: LogSink) -> int:
    """Flip non-terminal dims to INCOMPLETE and return how many were flipped.

    Covers ``pending`` as well as ``running``. A dimension the run never
    got to is just as unfinished as one interrupted mid-flight, and the
    state machine allows PENDING -> INCOMPLETE precisely for this. Leaving
    them at ``pending`` made a truncated run indistinguishable from a
    complete one: the scored dimensions were averaged into a run grade
    with no record that the rest never ran.
    """
    from quodeq.core.run.dimensions import DimState  # noqa: PLC0415 — signal path
    from quodeq.data.fs.dimensions_state_store import read_dimensions, write_dim_state
    try:
        entries = read_dimensions(run_dir).get("dimensions", {})
    except (TypeError, AttributeError) as exc:  # a run_dir that isn't a real
        # Path, or a dimensions.json that parses but isn't an object (e.g. `[]`)
        log.warning(f"failed to read dimensions for flip: {exc}")
        return 0
    flipped = 0
    for dim, entry in entries.items():
        if isinstance(entry, dict) and entry.get("state") in {DimState.RUNNING, DimState.PENDING}:
            try:
                write_dim_state(run_dir, dim, DimState.INCOMPLETE, reason=reason)
                flipped += 1
            except Exception as exc:  # noqa: BLE001
                log.warning(f"failed to mark dim {dim} incomplete: {exc}")
    return flipped


def is_named_error(exc_type: type[BaseException] | None, name: str) -> bool:
    """Detect an analysis-layer error class without a hard import dependency.

    Lifecycle is a shared/low-level module; importing from analysis would
    invert the dependency graph. Class-name match is enough since we
    control both ends.
    """
    if exc_type is None:
        return False
    return any(cls.__name__ == name for cls in exc_type.__mro__)


def is_circuit_breaker_error(exc_type: type[BaseException] | None) -> bool:
    return is_named_error(exc_type, "CircuitBreakerError")


def seed_dimension_states(
    run_dir: Path, dimensions: list[str], *, log: LogSink,
) -> None:
    """Initialise dimensions.json with one PENDING entry per dim."""
    from quodeq.core.run.dimensions import DimState  # noqa: PLC0415
    from quodeq.data.fs.dimensions_state_store import write_dim_state  # noqa: PLC0415
    for dim in dimensions:
        try:
            write_dim_state(run_dir, dim, DimState.PENDING)
        except Exception as exc:  # noqa: BLE001
            log.warning(f"failed to seed dim state for {dim}: {exc}")


def run_signal_shutdown(
    heartbeat: _Stoppable, resources: _Stoppable, status: _StatusWriter, signum: int, *, log: LogSink,
) -> None:
    """Write CANCELLED status and close out unfinished dims for a caught signal.

    ``status`` is the run's ``_StatusWriter``: it supplies the run dir the
    dim states live in and the deadline the signal is judged against.

    A signal landing AFTER the run's own deadline is the watchdog enforcing
    the time budget (SIGTERM at deadline+grace), not a user cancel. Label it
    "deadline" — the UI maps that to "time limit reached", not an error —
    and close out running dims. The state stays CANCELLED either way:
    salvage scoring triggers key off terminal failed/cancelled and must
    keep firing.

    Signals worker threads (subagent pool, AI CLI subprocess monitors) to
    stop waiting on long-running operations and terminate promptly. Avoids
    the transition-validating path — the caller may be mid-state.

    Closes out every unfinished dim, not just on the deadline path: a plain
    cancel left the in-flight dimension stuck at 'running' and the
    untouched ones at 'pending' for the life of the run dir.

    Caller (``RunLifecycleContext._handle_signal``) still owns setting its
    own ``_current_state`` and raising ``SystemExit`` -- those touch state
    this function has no access to.
    """
    try:
        name = signal.Signals(signum).name
    except ValueError:
        name = f"signal_{signum}"
    deadline_enforced = _deadline_has_passed(status.deadline_at)
    exit_reason = ExitReason.DEADLINE if deadline_enforced else f"signal_{name}"
    cancellation.request_cancel()
    heartbeat.stop()
    resources.stop()
    status.write(RunState.CANCELLED, exit_reason=exit_reason)
    mark_unfinished_dims_incomplete(
        status.run_dir, ExitReason.TIME_LIMIT if deadline_enforced else ExitReason.CANCELLED, log=log)


def finalize_run_on_atexit(
    run_dir: Path, heartbeat: _Stoppable, resources: _Stoppable, status: _StatusWriter,
) -> None:
    """Write CANCELLED status if the process is exiting without a terminal state."""
    current = read_status(run_dir)
    if current is None:
        return
    state_str = current.get("state")
    if state_str in TERMINAL_STATES:
        return
    heartbeat.stop()
    resources.stop()
    status.write(RunState.CANCELLED, exit_reason="atexit_unfinalized")
