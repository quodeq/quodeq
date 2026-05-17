"""SSE watcher and event serializers for /api/evaluations/<jobId>/events.

Producers (lifecycle context, scoring engine, FindingsRouter) write durable
artifacts (status.json, evaluation/<dim>.json, events.jsonl). This module
observes those artifacts on a 250 ms tick and emits SSE events to subscribers.

Reconnect via Last-Event-ID is supported by ISO 8601 timestamps stored in
events.jsonl (the run event log written by EventLogWriter / FindingsRouter).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

_DEFAULT_FINDINGS_BATCH = 500
"""Per-tick cap on findings pulled from the event log for the SSE stream.

Bounds the initial-snapshot burst so a run with tens of thousands of findings
cannot OOM the API process. Subsequent ticks resume from the last event
timestamp via the SSE Last-Event-ID mechanism.
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


def serialize_scores_updated_event(payload: dict[str, Any]) -> str:
    """Return the SSE data: payload for an `event: scores.updated` frame.

    Payload matches the /api/projects/<p>/scores/<run> response shape.
    """
    return json.dumps(payload, separators=(",", ":"))


@dataclass
class WatcherState:
    """Mutable per-stream state. Tracks what has been emitted to one client.

    last_event_ts is the ISO 8601 timestamp cursor for resuming from events.jsonl
    on reconnect (via Last-Event-ID). last_event_counter is a sequential integer
    used as finding `id` in the payload for client backward-compatibility.
    last_grade_completed_at is the MAX(completed_at) from dimension_scores the
    last time a scores.updated event was emitted; None means never checked.
    """
    last_event_ts: datetime | None = None
    last_event_counter: int = 0
    last_status_mtime: float | None = None
    emitted_dimensions: frozenset[str] = field(default_factory=frozenset)
    last_grade_completed_at: str | None = None


_logger = logging.getLogger(__name__)

_DIM_FILENAME_SUFFIX = ".json"

EventTuple = tuple[str, str, str | None]
"""(event_type, payload, optional_event_id) — event_id is ISO timestamp for findings, None for others."""


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


def _payload_as_sse_finding(payload: Any, finding_id: int) -> dict[str, Any]:
    """Project a Judgment into the finding dict the SSE client expects."""
    return {
        "id": finding_id,
        "practice_id": payload.practice_id,
        "dimension": payload.dimension,
        "requirement": getattr(payload, "req", None),
        "verdict": payload.verdict,
        "severity": payload.severity,
        "file": payload.file,
        "line": payload.line,
        "end_line": payload.end_line,
        "title": payload.title,
        "reason": payload.reason,
        "snippet": payload.snippet,
        "confidence": payload.confidence,
    }


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
        from quodeq.core.events.reader import EventLogReader  # noqa: PLC0415
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

    # --- scores.updated branch ---
    # Trigger projection (cheap no-op if no JSONL/actions log activity since last tick).
    # This applies any actions.jsonl events so grade tables stay current.
    grade_event: EventTuple | None = None
    new_grade_completed_at = state.last_grade_completed_at
    try:
        from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository  # noqa: PLC0415
        repo = SqliteFindingsRepository(run_dir)
        if repo._events_log.is_file():  # noqa: SLF001
            project_dir = run_dir.parent.parent
            repo._projector.ensure_projected(  # noqa: SLF001
                repo._events_log, run_dir, project_dir=project_dir,  # noqa: SLF001
            )
    except Exception:
        _logger.warning("SSE tick: ensure_fresh failed for %s", run_dir, exc_info=True)

    try:
        from quodeq.data.sqlite.connection import open_evaluation_db  # noqa: PLC0415
        with open_evaluation_db(run_dir) as conn:
            rows = conn.execute(
                "SELECT dimension, score, grade, completed_at FROM dimension_scores ORDER BY dimension",
            ).fetchall()
        # Fingerprint captures both the grade values and the MAX(completed_at).
        # This detects: grades advancing, grades changing value, and all grades
        # being dismissed (table becomes empty after a full-dismiss recompute).
        current_fingerprint = repr(rows) if rows else None
        if current_fingerprint != state.last_grade_completed_at:
            from quodeq.services.scoring import get_scores_raw  # noqa: PLC0415
            # run_dir layout: <reports_root>/<project>/runs/<run_id>
            reports_root = run_dir.parent.parent.parent
            project = run_dir.parent.parent.name
            run_id = run_dir.name
            payload = get_scores_raw(reports_root, project, run_id)
            grade_event = ("scores.updated", serialize_scores_updated_event(payload), None)
            new_grade_completed_at = current_fingerprint
    except Exception:
        _logger.warning("SSE tick: scores.updated build failed for %s", run_dir, exc_info=True)

    if grade_event is not None:
        events.append(grade_event)

    new_state = WatcherState(
        last_event_ts=new_last_ts,
        last_event_counter=new_counter,
        last_status_mtime=status_mtime,
        emitted_dimensions=frozenset(state.emitted_dimensions | set(new_dims)),
        last_grade_completed_at=new_grade_completed_at,
    )
    return events, new_state


import os
import time
from typing import Iterator

from quodeq.api._sse_log_helpers import sse_line

_TICK_MS = int(os.environ.get("QUODEQ_SSE_TICK_MS", "250"))
_HEARTBEAT_S = float(os.environ.get("QUODEQ_SSE_HEARTBEAT_S", "15"))
_TERMINAL_STATES = frozenset({"done", "failed", "cancelled"})


def _is_terminal(status_payload: str) -> tuple[bool, str]:
    """Check whether the JSON status payload represents a terminal state."""
    try:
        data = json.loads(status_payload)
    except ValueError:
        return False, ""
    state = data.get("state") if isinstance(data, dict) else None
    if isinstance(state, str) and state in _TERMINAL_STATES:
        return True, state
    return False, ""


def run_events_generator(
    run_dir: Path,
    *,
    last_event_ts: datetime | None = None,
    tick_seconds: float | None = None,
    heartbeat_seconds: float | None = None,
) -> Iterator[str]:
    """Yield SSE frames observing run_dir.

    tick_seconds overrides QUODEQ_SSE_TICK_MS for tests (use 0.0 to drain
    immediately without sleeping).
    heartbeat_seconds overrides the 15s :keepalive interval for tests.

    The try/finally is defensive: today no per-stream resources persist
    between ticks (every helper opens and closes its own file handle),
    so cleanup is a no-op. The block exists so a future change that adds
    a longer-lived resource has a place to release it.
    """
    sleep_s = tick_seconds if tick_seconds is not None else (_TICK_MS / 1000.0)
    heartbeat_s = heartbeat_seconds if heartbeat_seconds is not None else _HEARTBEAT_S
    state = WatcherState(last_event_ts=last_event_ts)
    last_emit_at = time.monotonic()
    yield ":keepalive\n\n"

    try:
        while True:
            events, state = compute_tick(run_dir, state)
            terminal_state = ""
            for event_type, payload, event_id in events:
                yield sse_line(payload, event=event_type, event_id=event_id)
                last_emit_at = time.monotonic()
                if event_type == "status":
                    done, terminal = _is_terminal(payload)
                    if done:
                        terminal_state = terminal

            if terminal_state:
                yield sse_line(
                    json.dumps({"state": terminal_state}, separators=(",", ":")),
                    event="done",
                )
                return

            if time.monotonic() - last_emit_at >= heartbeat_s:
                yield ":keepalive\n\n"
                last_emit_at = time.monotonic()

            if sleep_s > 0:
                time.sleep(sleep_s)
            else:
                # tick_seconds=0.0 means "drain once and exit" for tests.
                return
    finally:
        # Reserved for future cleanup of long-lived per-stream resources.
        # Currently a no-op because each tick opens and closes its own handles.
        pass
