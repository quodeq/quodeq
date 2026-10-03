"""Per-tick orchestration for the SSE run-event watcher.

Combines the artifact readers in ``services/run_event_readers.py`` with the
SSE serializers in ``_run_event_serializers.py`` to produce the
(event_type, payload, event_id) tuples the stream generator emits. Split out
of _run_event_stream.py purely for file size. The readers themselves (and
their constants) are re-exported here for backward-compatible imports (tests
and _run_event_stream.py import them from this module).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from quodeq.api.sse_frames import SseEvent
from quodeq.api._run_event_serializers import (
    serialize_dimension_event,
    serialize_finding_event,
    serialize_status_event,
    payload_as_sse_finding,
)
from quodeq.services.live_finding_filter import LiveFindingFilter
from quodeq.services.run_event_readers import (  # noqa: F401 — re-export
    DEFAULT_FINDINGS_BATCH,
    STATUS_MTIME_MISSING,
    findings_batch_size,
    read_dim_eval,
    read_new_findings_from_events,
    read_status,
    scan_completed_dimensions,
)
from quodeq.shared.log_sink import LoggerSink

_logger = logging.getLogger(__name__)
_LOG = LoggerSink(_logger)

EventTuple = tuple[str, str, str | None]
"""(event_type, payload, optional_event_id) — event_id is ISO timestamp for findings, None for others."""


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
    # Decides which judgments become ``finding`` frames (violations only, deduped,
    # suppression and standard applied). Holds the per-stream dedup set, so it is
    # built on the first tick and carried across the rest of the connection.
    finding_filter: LiveFindingFilter | None = field(default=None, repr=False, compare=False)


def _finding_events(
    run_dir: Path, state: WatcherState, finding_filter: LiveFindingFilter,
) -> tuple[list[EventTuple], datetime | None, int]:
    """The ``finding`` frames for the judgments logged since the cursor, plus the new cursor.

    The cursor moves past every judgment read, admitted or not, so a
    compliance row is never re-read on the next tick. A read or shaping
    failure yields no frames and leaves the cursor where it was.
    """
    new_last_ts = state.last_event_ts
    new_counter = state.last_event_counter
    try:
        new_findings = read_new_findings_from_events(
            run_dir, state.last_event_ts, state.last_event_counter,
        )
        if new_findings:
            finding_filter.refresh()
        finding_events: list[EventTuple] = []
        for event_ts, counter, payload in new_findings:
            new_last_ts = event_ts
            new_counter = counter
            if not finding_filter.admits(payload):
                continue
            finding_dict = payload_as_sse_finding(payload, counter)
            finding_events.append((SseEvent.FINDING, serialize_finding_event(finding_dict), event_ts.isoformat()))
    except (OSError, ValueError, TypeError) as exc:
        _LOG.warning(f"events.jsonl read failed for {run_dir}: {exc}")
        return [], state.last_event_ts, state.last_event_counter
    return finding_events, new_last_ts, new_counter


def compute_tick(run_dir: Path, state: WatcherState) -> tuple[list[EventTuple], WatcherState]:
    """Single tick: read artifacts, return (events, new_state).

    Defensive against every artifact being absent or malformed.
    Status mtime tracking ensures unchanged status is not re-emitted.
    Dimension set tracking ensures completed dimensions are not re-emitted.
    Finding id advances only when new rows are read.
    """
    events: list[EventTuple] = []

    # --- Status ---
    status, status_mtime = read_status(run_dir, log=_LOG)
    if status_mtime != state.last_status_mtime:
        events.append((SseEvent.STATUS, serialize_status_event(status), None))

    # --- Dimensions ---
    completed = scan_completed_dimensions(run_dir)
    new_dims = sorted(completed - state.emitted_dimensions)
    for dim in new_dims:
        eval_data = read_dim_eval(run_dir, dim, log=_LOG)
        events.append((SseEvent.DIMENSION_COMPLETED, serialize_dimension_event(
            dimension=dim, eval_data=eval_data,
        ), None))

    # --- Findings ---
    finding_filter = state.finding_filter or LiveFindingFilter(run_dir, log=_LOG)
    finding_events, new_last_ts, new_counter = _finding_events(run_dir, state, finding_filter)
    events.extend(finding_events)

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
        finding_filter=finding_filter,
    )
    return events, new_state
