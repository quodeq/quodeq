"""Signal-guard, atexit-guard, and exit-classification helpers for
RunLifecycleContext.

Split out of ``run_lifecycle.py`` (file-size ratchet): these are
self-contained process-level primitives and pure helpers with no dependency
on the lifecycle state machine itself (the exception -> state mapping in
``__exit__``), so they compose cleanly as standalone collaborators owned by
``RunLifecycleContext``.

``_StatusWriter`` stays in ``run_lifecycle.py`` rather than moving here: it
calls ``write_status`` by bare name, and
``tests/analysis/test_run_lifecycle.py`` patches that name at
``quodeq.analysis.run_lifecycle.write_status`` -- moving the caller would
silently break that patch.
"""
from __future__ import annotations

import atexit
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quodeq.core.observability import LogSink
from quodeq.shared import cancellation
from quodeq.data.fs.run_status_store import RunState, TERMINAL_STATES, read_status

_SIGNALS_TO_HANDLE = (signal.SIGINT, signal.SIGTERM)
# SIGHUP is POSIX-only. Included conditionally below.
if hasattr(signal, "SIGHUP"):
    _SIGNALS_TO_HANDLE = _SIGNALS_TO_HANDLE + (signal.SIGHUP,)


class _SignalGuard:
    """Install *handler* on the run's signals; restore the originals after."""

    def __init__(self, handler: Any) -> None:
        self._handler = handler
        self._previous: dict[int, Any] = {}

    def install(self) -> None:
        for sig in _SIGNALS_TO_HANDLE:
            try:
                self._previous[sig] = signal.getsignal(sig)
                signal.signal(sig, self._handler)
            except (OSError, ValueError):
                # Can fail in non-main threads; tests may run under such a case.
                pass

    def restore(self) -> None:
        for sig, prev in self._previous.items():
            try:
                signal.signal(sig, prev)
            except (OSError, ValueError):
                pass
        self._previous.clear()


class _AtexitGuard:
    """Register *callback* with atexit once, and deregister it once."""

    def __init__(self, callback: Any) -> None:
        self._callback = callback
        self._registered = False

    def register(self) -> None:
        atexit.register(self._callback)
        self._registered = True

    def deregister(self) -> None:
        if not self._registered:
            return
        try:
            atexit.unregister(self._callback)
        except Exception:
            pass
        self._registered = False


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


def _mark_unfinished_dims_incomplete(
    run_dir: Path, reason: str, *, log: LogSink,
) -> int:
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
        entries = read_dimensions(run_dir).get("dimensions", {})
    except Exception:  # noqa: BLE001 — a failing flip must not mask the exit
        return 0
    flipped = 0
    for dim, entry in entries.items():
        if isinstance(entry, dict) and entry.get("state") in {"running", "pending"}:
            try:
                write_dim_state(run_dir, dim, DimState.INCOMPLETE, reason=reason)
                flipped += 1
            except Exception as exc:  # noqa: BLE001
                log.warning(f"failed to mark dim {dim} incomplete: {exc}")
    return flipped


def _is_named_error(exc_type: type[BaseException] | None, name: str) -> bool:
    """Detect an analysis-layer error class without a hard import dependency.

    Lifecycle is a shared/low-level module; importing from analysis would
    invert the dependency graph. Class-name match is enough since we
    control both ends.
    """
    if exc_type is None:
        return False
    return any(cls.__name__ == name for cls in exc_type.__mro__)


def _is_circuit_breaker_error(exc_type: type[BaseException] | None) -> bool:
    return _is_named_error(exc_type, "CircuitBreakerError")


def _seed_dimension_states(
    run_dir: Path, dimensions: list[str], *, log: LogSink,
) -> None:
    """Initialise dimensions.json with one PENDING entry per dim."""
    from quodeq.data.fs.dimensions_state_store import DimState, write_dim_state  # noqa: PLC0415
    for dim in dimensions:
        try:
            write_dim_state(run_dir, dim, DimState.PENDING)
        except Exception as exc:  # noqa: BLE001
            log.warning(f"failed to seed dim state for {dim}: {exc}")


def _run_signal_shutdown(
    run_dir: Path, heartbeat: Any, resources: Any, status: Any,
    deadline_at: str | None, signum: int, *, log: LogSink,
) -> None:
    """Write CANCELLED status and close out unfinished dims for a caught signal.

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
    deadline_enforced = _deadline_has_passed(deadline_at)
    exit_reason = "deadline" if deadline_enforced else f"signal_{name}"
    cancellation.request_cancel()
    heartbeat.stop()
    resources.stop()
    status.write(RunState.CANCELLED, exit_reason=exit_reason)
    _mark_unfinished_dims_incomplete(
        run_dir, "time_limit" if deadline_enforced else "cancelled", log=log)


def _finalize_run_on_atexit(
    run_dir: Path, heartbeat: Any, resources: Any, status: Any,
) -> None:
    """Write CANCELLED status if the process is exiting without a terminal state."""
    current = read_status(run_dir)
    if current is None:
        return
    state_str = current.get("state")
    if state_str in {s.value for s in TERMINAL_STATES}:
        return
    heartbeat.stop()
    resources.stop()
    status.write(RunState.CANCELLED, exit_reason="atexit_unfinalized")
