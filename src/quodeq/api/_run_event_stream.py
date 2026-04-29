"""SSE watcher and event serializers for /api/evaluations/<jobId>/events.

Producers (lifecycle context, scoring engine, FindingsRouter) write durable
artifacts (status.json, evaluation/<dim>.json, evaluation.db). This module
observes those artifacts on a 250 ms tick and emits SSE events to subscribers.

No producer changes. No in-memory event log. No cross-stream state.
Reconnect via Last-Event-ID is supported by SQLite's autoincrement findings.id.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


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
