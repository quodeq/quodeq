"""Per-dimension lifecycle state for an evaluation run.

Mirrors run_status.py for the per-dim layer. Lives in a sibling
dimensions.json so per-dim writers don't contend with the run-level
status writer's lock.
"""
from __future__ import annotations

import enum
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
FILENAME = "dimensions.json"


class DimState(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    INCOMPLETE = "incomplete"


_TERMINAL = frozenset({DimState.DONE, DimState.INCOMPLETE})

_ALLOWED: dict[DimState, frozenset[DimState]] = {
    DimState.PENDING: frozenset({DimState.RUNNING, DimState.INCOMPLETE}),
    DimState.RUNNING: frozenset({DimState.DONE, DimState.INCOMPLETE}),
    DimState.DONE: frozenset(),
    DimState.INCOMPLETE: frozenset(),
}


class IllegalDimTransitionError(RuntimeError):
    pass


_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_dimensions(run_dir: Path) -> dict[str, Any]:
    path = run_dir / FILENAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, FileNotFoundError, json.JSONDecodeError):
        return {"schema_version": SCHEMA_VERSION, "dimensions": {}}


def write_dim_state(
    run_dir: Path, dimension: str, state: DimState,
    *, reason: str | None = None,
) -> None:
    """Transition *dimension* to *state* atomically.

    Validates the transition against the state machine. Initial writes
    (no prior entry) are allowed regardless of *state* -- callers can seed
    in any state, but typically use PENDING first.
    """
    with _lock:
        data = read_dimensions(run_dir)
        existing = data["dimensions"].get(dimension)
        if existing is not None:
            try:
                prev = DimState(existing["state"])
            except ValueError:
                prev = DimState.PENDING
            if state not in _ALLOWED[prev]:
                raise IllegalDimTransitionError(
                    f"{dimension}: {prev.value} -> {state.value} not permitted",
                )
        entry: dict[str, Any] = {"state": state.value}
        if state == DimState.RUNNING:
            entry["started_at"] = _now_iso()
        elif state == DimState.DONE:
            entry["completed_at"] = _now_iso()
        elif state == DimState.INCOMPLETE:
            entry["interrupted_at"] = _now_iso()
            if reason:
                entry["reason"] = reason
        data["dimensions"][dimension] = entry
        data["schema_version"] = SCHEMA_VERSION

        run_dir.mkdir(parents=True, exist_ok=True)
        tmp = run_dir / (FILENAME + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(run_dir / FILENAME)
