"""Per-dimension lifecycle state machine (pure; persistence in data/fs).

Mirrors ``core/run/state.py`` for the per-dimension layer. Reading and
writing ``dimensions.json`` lives in ``data/fs/dimensions_state_store.py``.
"""
from __future__ import annotations

import enum

SCHEMA_VERSION = 1
FILENAME = "dimensions.json"


class DimState(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    INCOMPLETE = "incomplete"


_ALLOWED: dict[DimState, frozenset[DimState]] = {
    DimState.PENDING: frozenset({DimState.RUNNING, DimState.INCOMPLETE}),
    DimState.RUNNING: frozenset({DimState.DONE, DimState.INCOMPLETE}),
    DimState.DONE: frozenset(),
    DimState.INCOMPLETE: frozenset(),
}


class IllegalDimTransitionError(RuntimeError):
    pass


def validate_dim_transition(dimension: str, prev: DimState, dst: DimState) -> None:
    """Raise IllegalDimTransitionError if *prev -> dst* is not permitted."""
    if dst not in _ALLOWED[prev]:
        raise IllegalDimTransitionError(
            f"{dimension}: {prev.value} -> {dst.value} not permitted",
        )
