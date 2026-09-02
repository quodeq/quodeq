"""Per-tick artifact reader for the SSE run-event watcher.

Reads status.json, evaluation/<dim>.json, and events.jsonl and turns them
into the (event_type, payload, event_id) tuples the stream generator emits.
Split out of _run_event_stream.py purely for file size.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from quodeq.api._run_event_serializers import (
    serialize_dimension_event,
    serialize_finding_event,
    serialize_status_event,
    _payload_as_sse_finding,
)

_logger = logging.getLogger(__name__)

_DEFAULT_FINDINGS_BATCH = 500
"""Per-tick cap on findings pulled from the event log for the SSE stream.

Bounds the initial-snapshot burst so a run with tens of thousands of findings
cannot OOM the API process. Subsequent ticks resume from the last event
timestamp via the SSE Last-Event-ID mechanism.
"""

_DIM_FILENAME_SUFFIX = ".json"

EventTuple = tuple[str, str, str | None]
"""(event_type, payload, optional_event_id) — event_id is ISO timestamp for findings, None for others."""

_STATUS_MTIME_MISSING: float = 0.0
"""Sentinel mtime used when status.json does not exist.

WatcherState initialises last_status_mtime=None ("never checked"), which is
distinct from 0.0 ("checked, file absent"). This ensures the pending status
is always emitted on the very first tick even when there is no status.json.
"""


def _findings_batch_size() -> int:
    raw = os.environ.get("QUODEQ_SSE_FINDINGS_BATCH")
    if not raw:
        return _DEFAULT_FINDINGS_BATCH
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_FINDINGS_BATCH
    return value if value > 0 else _DEFAULT_FINDINGS_BATCH


@dataclass
class WatcherState:
    """Mutable per-stream state. Tracks what has been emitted to one client.

    last_event_ts is the ISO 8601 timestamp cursor for resuming from events.jsonl
    on reconnect (via Last-Event-ID). last_event_counter is a sequential integer
    used as finding `id` in the payload for client backward-compatibility.

    Grade updates intentionally do NOT live on the SSE stream — mutations
    (dismiss / restore / delete) return the rescored payload synchronously
    from their HTTP response. SSE is reserved for in-progress eval tracking:
    new findings, dimension completions, status transitions, terminal done.
    """
    last_event_ts: datetime | None = None
    last_event_counter: int = 0
    last_status_mtime: float | None = None
    emitted_dimensions: frozenset[str] = field(default_factory=frozenset)


def _read_status(run_dir: Path) -> tuple[dict[str, Any], float]:
    """Read status.json. Returns ({state: pending}, 0.0) when the file is absent."""
    path = run_dir / "status.json"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {"state": "pending"}, _STATUS_MTIME_MISSING
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
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
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError) as exc:
        _logger.warning("dimension eval read failed at %s: %s", path, exc)
        return None


def _read_new_findings_from_events(
    run_dir: Path,
    last_event_ts: datetime | None,
    counter_start: int,
) -> list[tuple[datetime, int, dict[str, Any]]]:
    """Return (event_ts, counter, finding_dict) triples for new JUDGMENT_CREATED events.

    Reads from run_dir/events.jsonl via EventLogReader.stream(since_timestamp).
    Caps at _findings_batch_size() results per call so a large initial snapshot
    cannot OOM the API process. Subsequent ticks resume via last_event_ts.
    """
    events_log = run_dir / "events.jsonl"
    if not events_log.is_file():
        return []
    try:
        from quodeq.services.run_events import EventLogReader  # noqa: PLC0415
        from quodeq.core.events.models import EventType  # noqa: PLC0415
        results: list[tuple[datetime, int, dict[str, Any]]] = []
        counter = counter_start
        batch_limit = _findings_batch_size()
        for event in EventLogReader(events_log).stream(since_timestamp=last_event_ts):
            if event.event_type != EventType.JUDGMENT_CREATED:
                continue
            counter += 1
            results.append((event.timestamp, counter, _payload_as_sse_finding(event.payload, counter)))
            if len(results) >= batch_limit:
                break
        return results
    except Exception as exc:  # noqa: BLE001 — never crash the stream on read errors
        _logger.warning("events.jsonl read failed for %s: %s", run_dir, exc)
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
    new_findings = _read_new_findings_from_events(
        run_dir, state.last_event_ts, state.last_event_counter,
    )
    new_last_ts = state.last_event_ts
    new_counter = state.last_event_counter
    for event_ts, counter, judgment_dict in new_findings:
        events.append(("finding", serialize_finding_event(judgment_dict), event_ts.isoformat()))
        new_last_ts = event_ts
        new_counter = counter

    # NOTE: scores.updated used to be emitted here on every tick by reading
    # dimension_scores / principle_grades and fingerprinting them. That whole
    # design ate four PRs (#525-#528) of bugs — fingerprint blind spots,
    # 1-second SQLite timestamps, terminal-status closure, principle-id
    # mismatches. The pipeline is now mutation-driven: ``POST /api/findings/*``
    # returns the rescored payload synchronously. SSE only carries lifecycle
    # events for in-progress evals (status, finding, dimension-completed, done).
    new_state = WatcherState(
        last_event_ts=new_last_ts,
        last_event_counter=new_counter,
        last_status_mtime=status_mtime,
        emitted_dimensions=frozenset(state.emitted_dimensions | set(new_dims)),
    )
    return events, new_state
