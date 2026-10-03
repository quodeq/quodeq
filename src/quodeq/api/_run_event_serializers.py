"""SSE payload serializers for /api/evaluations/<jobId>/events."""
from __future__ import annotations

import json
from typing import Any


def sse_json(payload: Any) -> str:
    """Compact JSON (no spaces after separators) for one SSE ``data:`` line."""
    return json.dumps(payload, separators=(",", ":"))


def serialize_status_event(status: dict[str, Any]) -> str:
    """Return the SSE data: payload for an `event: status` frame."""
    return sse_json(status)


def serialize_dimension_event(*, dimension: str, eval_data: dict[str, Any] | None) -> str:
    """Return the SSE data: payload for an `event: dimension-completed` frame.

    eval_data is the parsed contents of evaluation/<dim>.json when available.
    On read failure or missing file, only the dimension name is emitted.
    """
    if eval_data is None:
        return sse_json({"dimension": dimension})
    return sse_json(eval_data)


def serialize_finding_event(judgment_dict: dict[str, Any]) -> str:
    """Return the SSE data: payload for an `event: finding` frame.

    judgment_dict is the row dict returned by SqliteFindingsRepository.list_*
    converted via _judgment_as_dict.
    """
    return sse_json(judgment_dict)


def payload_as_sse_finding(payload: Any, finding_id: int) -> dict[str, Any]:
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
