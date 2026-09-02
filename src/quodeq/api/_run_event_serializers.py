"""SSE payload serializers for /api/evaluations/<jobId>/events.

Split out of _run_event_stream.py purely for file size; nothing here is
patch-tested by name (tests import these directly).
"""
from __future__ import annotations

import json
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
        "provenance_downgrade": getattr(payload, "provenance_downgrade", False),
        "scope_downgrade": getattr(payload, "scope_downgrade", None),
        "carried_forward": getattr(payload, "carried_forward", False),
    }
