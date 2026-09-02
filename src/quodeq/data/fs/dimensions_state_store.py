"""Reads/writes ``{run_dir}/dimensions.json`` (state machine in core/run/dimensions).

Lives in a sibling dimensions.json so per-dim writers don\'t contend with the
run-level status writer\'s lock.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quodeq.core.run.dimensions import (  # noqa: F401 — re-exported API
    FILENAME,
    SCHEMA_VERSION,
    DimState,
    IllegalDimTransitionError,
    validate_dim_transition,
)

_logger = logging.getLogger(__name__)

_lock = threading.Lock()

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_dimensions(run_dir: Path) -> dict[str, Any]:
    path = run_dir / FILENAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, FileNotFoundError, json.JSONDecodeError):
        return {"schema_version": SCHEMA_VERSION, "dimensions": {}}


def _apply_state_transition(
    entry: dict[str, Any], state: DimState,
    *, reason: str | None = None, exit_reason: str | None = None,
) -> dict[str, Any]:
    """Return *entry* updated for the RUNNING/DONE/INCOMPLETE transition.

    Mutates and returns *entry* in place. See write_dim_state for why each
    transition merges into the existing record instead of replacing it.
    """
    entry["state"] = state.value
    if state == DimState.RUNNING:
        entry["started_at"] = _now_iso()
    elif state == DimState.DONE:
        entry["completed_at"] = _now_iso()
        if exit_reason is not None:
            entry["exit_reason"] = exit_reason
    elif state == DimState.INCOMPLETE:
        entry["interrupted_at"] = _now_iso()
        if reason:
            entry["reason"] = reason
    return entry


def write_dim_state(
    run_dir: Path, dimension: str, state: DimState,
    *, reason: str | None = None, exit_reason: str | None = None,
) -> None:
    """Transition *dimension* to *state* atomically.

    Validates the transition against the state machine. Initial writes
    (no prior entry) are allowed regardless of *state* -- callers can seed
    in any state, but typically use PENDING first.

    Optional ``exit_reason`` attaches to the per-dim record on DONE, e.g.
    "done", "time_limit", "failure_streak", "cancelled", "error". The UI
    treats anything other than "done" as a partial-coverage signal.

    Each transition merges into the existing record instead of replacing
    it, so ``started_at`` (stamped on RUNNING) survives the DONE/INCOMPLETE
    write — progress reads ``completed_at - started_at`` for a dimension's
    duration. Safe because DONE and INCOMPLETE are terminal: no transition
    can ever need a field cleared.
    """
    with _lock:
        data = read_dimensions(run_dir)
        existing = data["dimensions"].get(dimension)
        if existing is not None:
            try:
                prev = DimState(existing["state"])
            except ValueError:
                _logger.warning(
                    "dimensions.json: corrupt state %r for %s; treating as pending",
                    existing.get("state"), dimension,
                )
                prev = DimState.PENDING
            validate_dim_transition(dimension, prev, state)
        entry: dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}
        data["dimensions"][dimension] = _apply_state_transition(
            entry, state, reason=reason, exit_reason=exit_reason,
        )
        data["schema_version"] = SCHEMA_VERSION

        run_dir.mkdir(parents=True, exist_ok=True)
        tmp = run_dir / (FILENAME + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(run_dir / FILENAME)
