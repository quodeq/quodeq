"""Per-dimension lifecycle state machine (pure; persistence in data/fs).

Mirrors ``core/run/state.py`` for the per-dimension layer. Reading and
writing ``dimensions.json`` lives in ``data/fs/dimensions_state_store.py``.
"""
from __future__ import annotations

import enum

SCHEMA_VERSION = 1
FILENAME = "dimensions.json"


class DimState(enum.StrEnum):
    """The states one dimension passes through inside a run.

    ``DONE`` and ``INCOMPLETE`` are terminal: a dimension that finished or
    gave up is never restarted within the same run. StrEnum (not a bare
    ``(str, enum.Enum)`` mixin) so ``str()``/f-strings/``%s`` render the
    plain value ("done") instead of "DimState.DONE".
    """

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
    """Raised by ``validate_dim_transition`` for a move the state machine forbids."""


def validate_dim_transition(dimension: str, prev: DimState, dst: DimState) -> None:
    """Raise IllegalDimTransitionError if *prev -> dst* is not permitted."""
    if dst not in _ALLOWED[prev]:
        raise IllegalDimTransitionError(
            f"{dimension}: {prev.value} -> {dst.value} not permitted",
        )
