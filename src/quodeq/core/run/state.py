"""Run lifecycle state machine (pure; persistence in data/fs/run_status_store).

CONTEXT.md defines **Run** as a first-class domain concept; the states and
allowed transitions below are its invariants and belong to core. Reading and
writing ``status.json`` lives in ``data/fs/run_status_store.py``.
"""
from __future__ import annotations

import enum

SCHEMA_VERSION = 2
STATUS_FILENAME = "status.json"


class RunState(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    FINALIZING = "finalizing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATES: frozenset[RunState] = frozenset({RunState.DONE, RunState.FAILED, RunState.CANCELLED})

# Allowed transitions (src -> set of dst). All other transitions raise.
_ALLOWED_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.PENDING: frozenset({RunState.RUNNING, RunState.CANCELLED, RunState.FAILED}),
    RunState.RUNNING: frozenset({RunState.FINALIZING, RunState.CANCELLED, RunState.FAILED}),
    RunState.FINALIZING: frozenset({RunState.DONE, RunState.CANCELLED, RunState.FAILED}),
    # Terminal states accept no further transitions.
    RunState.DONE: frozenset(),
    RunState.FAILED: frozenset(),
    RunState.CANCELLED: frozenset(),
}


class IllegalTransitionError(RuntimeError):
    """Raised when a state transition is not permitted by the state machine."""


class UnsupportedSchemaError(RuntimeError):
    """Raised when status.json has a schema_version newer than this code supports."""


def validate_transition(src: RunState, dst: RunState) -> None:
    """Raise IllegalTransitionError if *src → dst* is not permitted."""
    allowed = _ALLOWED_TRANSITIONS.get(src, frozenset())
    if dst not in allowed:
        raise IllegalTransitionError(f"{src.value} → {dst.value} is not a permitted transition")
