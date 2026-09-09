"""Run lifecycle state machine (pure; persistence in data/fs/run_status_store).

CONTEXT.md defines **Run** as a first-class domain concept; the states and
allowed transitions below are its invariants and belong to core. Reading and
writing ``status.json`` lives in ``data/fs/run_status_store.py``.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = 2
STATUS_FILENAME = "status.json"


class RunState(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    FINALIZING = "finalizing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class RunStatus:
    """The full set of fields ``status.json`` can carry for one run.

    Passed to ``run_status_store.write_status`` instead of 13 separate
    keyword arguments; ``_build_status_payload`` maps this 1:1 onto the
    wire format (see that module for the exact key set and defaulting
    rules, which are unchanged by this type).
    """

    state: RunState
    job_id: str
    started_at: str
    dimensions: list[str]
    phase: str | None = None
    current_dimension: str | None = None
    pid: int | None = None
    exit_reason: str | None = None
    finalized_at: str | None = None
    deadline_at: str | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    time_limit_s: int | None = None

    @classmethod
    def from_status_dict(cls, d: dict[str, Any]) -> "RunStatus":
        """Rebuild a ``RunStatus`` from ``read_status()`` output (or a compatible dict)."""
        return cls(
            state=RunState(d["state"]),
            job_id=d.get("job_id", ""),
            started_at=d.get("started_at", ""),
            dimensions=d.get("dimensions") or [],
            phase=d.get("phase"),
            current_dimension=d.get("current_dimension"),
            pid=d.get("pid"),
            exit_reason=d.get("exit_reason"),
            finalized_at=d.get("finalized_at"),
            deadline_at=d.get("deadline_at"),
            ai_provider=d.get("ai_provider"),
            ai_model=d.get("ai_model"),
            time_limit_s=d.get("time_limit_s"),
        )


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
