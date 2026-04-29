"""SSE watcher and event serializers for /api/evaluations/<jobId>/events.

Producers (lifecycle context, scoring engine, FindingsRouter) write durable
artifacts (status.json, evaluation/<dim>.json, evaluation.db). This module
observes those artifacts on a 250 ms tick and emits SSE events to subscribers.

No producer changes. No in-memory event log. No cross-stream state.
Reconnect via Last-Event-ID is supported by SQLite's autoincrement findings.id.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quodeq.data.sqlite.connection import EVALUATION_DB_FILENAME


def serialize_status_event(status: dict[str, Any]) -> str:
    """Return the SSE data: payload for an `event: status` frame."""
    return json.dumps(status, separators=(",", ":"))


def serialize_dimension_event(*, dimension: str, eval_data: dict[str, Any] | None) -> str:
    """Return the SSE data: payload for an `event: dimension-completed` frame.

    eval_data is the parsed contents of evaluation/<dim>.json when available.
    On read failure or missing file, only the dimension name is emitted.
    """
    if eval_data is None:
        return json.dumps({"dimension": dimension}, separators=(",", ":"))
    return json.dumps(eval_data, separators=(",", ":"))


def serialize_finding_event(judgment_dict: dict[str, Any]) -> str:
    """Return the SSE data: payload for an `event: finding` frame.

    judgment_dict is the row dict returned by SqliteFindingsRepository.list_*
    converted via _judgment_as_dict (see Task 3).
    """
    return json.dumps(judgment_dict, separators=(",", ":"))


@dataclass
class WatcherState:
    """Mutable per-stream state. Tracks what has been emitted to one client.

    last_event_id advances only on `event: finding` (matches SSE Last-Event-ID
    semantics — status and dimension events are idempotent on reconnect).
    """
    last_event_id: int = 0
    last_status_mtime: float | None = None
    emitted_dimensions: frozenset[str] = field(default_factory=frozenset)


_logger = logging.getLogger(__name__)

_DIM_FILENAME_SUFFIX = ".json"

EventTuple = tuple[str, str, int | None]
"""(event_type, payload, optional_event_id) — event_id is None for non-finding events."""


_STATUS_MTIME_MISSING: float = 0.0
"""Sentinel mtime used when status.json does not exist.

WatcherState initialises last_status_mtime=None ("never checked"), which is
distinct from 0.0 ("checked, file absent"). This ensures the pending status
is always emitted on the very first tick even when there is no status.json.
"""


def _read_status(run_dir: Path) -> tuple[dict[str, Any], float]:
    """Read status.json. Returns ({state: pending}, 0.0) when the file is absent."""
    path = run_dir / "status.json"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {"state": "pending"}, _STATUS_MTIME_MISSING
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            return {"state": "pending"}, mtime
        return data, mtime
    except (OSError, ValueError) as exc:
        _logger.warning("status.json read failed at %s: %s", path, exc)
        return {"state": "pending"}, mtime


def _scan_completed_dimensions(run_dir: Path) -> set[str]:
    """Return the set of dimension names that have an evaluation/<dim>.json file."""
    eval_dir = run_dir / "evaluation"
    try:
        return {
            entry.name[: -len(_DIM_FILENAME_SUFFIX)]
            for entry in eval_dir.iterdir()
            if entry.is_file() and entry.name.endswith(_DIM_FILENAME_SUFFIX)
        }
    except OSError:
        return set()


def _read_dim_eval(run_dir: Path, dimension: str) -> dict[str, Any] | None:
    """Read evaluation/<dim>.json. Returns None on any failure.

    The returned dict's ``dimension`` key is the canonical dimension name as
    written by the scoring engine. Callers should treat that value as
    authoritative — it always matches the filename stem for well-formed files.
    """
    path = run_dir / "evaluation" / f"{dimension}{_DIM_FILENAME_SUFFIX}"
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else None
    except (OSError, ValueError) as exc:
        _logger.warning("dimension eval read failed at %s: %s", path, exc)
        return None


def _judgment_as_dict(judgment: Any, finding_id: int) -> dict[str, Any]:
    """Project a Judgment dataclass into a JSON-friendly dict for SSE."""
    return {
        "id": finding_id,
        "practice_id": judgment.practice_id,
        "dimension": judgment.dimension,
        "requirement": judgment.req,
        "verdict": judgment.verdict,
        "severity": judgment.severity,
        "file": judgment.file,
        "line": judgment.line,
        "end_line": judgment.end_line,
        "title": judgment.title,
        "reason": judgment.reason,
        "snippet": judgment.snippet,
    }


def _read_new_findings(
    run_dir: Path, last_event_id: int,
) -> list[tuple[int, dict[str, Any]]]:
    """Return (id, judgment_dict) pairs for findings whose id > last_event_id."""
    db_path = run_dir / EVALUATION_DB_FILENAME
    if not db_path.is_file():
        return []
    try:
        from quodeq.data.sqlite.connection import open_evaluation_db  # noqa: PLC0415
        from quodeq.data.sqlite._row_mappers import row_to_judgment  # noqa: PLC0415
        results: list[tuple[int, dict[str, Any]]] = []
        with open_evaluation_db(run_dir) as conn:
            cur = conn.execute(
                "SELECT id, practice_id, dimension, requirement, verdict, severity, "
                "file, line, end_line, title, reason, snippet, "
                "violation_type, context, scope, req_refs_json "
                "FROM findings WHERE id > ? ORDER BY id",
                (last_event_id,),
            )
            cols = [c[0] for c in cur.description]
            for row in cur.fetchall():
                row_dict = dict(zip(cols, row))
                finding_id = row_dict["id"]
                judgment = row_to_judgment(row_dict)
                results.append((finding_id, _judgment_as_dict(judgment, finding_id)))
        return results
    except Exception as exc:  # noqa: BLE001 — never crash the stream on read errors
        _logger.warning("findings query failed for %s: %s", run_dir, exc)
        return []


def compute_tick(run_dir: Path, state: WatcherState) -> tuple[list[EventTuple], WatcherState]:
    """Single tick: read artifacts, return (events, new_state).

    Defensive against every artifact being absent or malformed.
    Status mtime tracking ensures unchanged status is not re-emitted.
    Dimension set tracking ensures completed dimensions are not re-emitted.
    Finding id advances only when new rows are read.
    """
    events: list[EventTuple] = []

    # --- Status ---
    status, status_mtime = _read_status(run_dir)
    if status_mtime != state.last_status_mtime:
        events.append(("status", serialize_status_event(status), None))

    # --- Dimensions ---
    completed = _scan_completed_dimensions(run_dir)
    new_dims = sorted(completed - state.emitted_dimensions)
    for dim in new_dims:
        eval_data = _read_dim_eval(run_dir, dim)
        events.append(("dimension-completed", serialize_dimension_event(
            dimension=dim, eval_data=eval_data,
        ), None))

    # --- Findings ---
    new_findings = _read_new_findings(run_dir, state.last_event_id)
    new_last_id = state.last_event_id
    for finding_id, judgment_dict in new_findings:
        events.append(("finding", serialize_finding_event(judgment_dict), finding_id))
        new_last_id = max(new_last_id, finding_id)

    new_state = WatcherState(
        last_event_id=new_last_id,
        last_status_mtime=status_mtime,
        emitted_dimensions=frozenset(state.emitted_dimensions | set(new_dims)),
    )
    return events, new_state
