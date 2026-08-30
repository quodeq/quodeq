"""Serialization of the dashboard response.

Split out of ``dashboard``: this is the wire boundary — everything here turns
already-computed domain objects into the camelCase dict the UI consumes, and
nothing here reads history or resolves runs. Declared in
``tests/tools/test_serialization_boundary.py``.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from quodeq.core.types import DimensionResult, to_camel_dict

from quodeq.data.fs.report_parser.runs import RunInfo
from quodeq.services._dashboard_history import _DashboardPayload


def _attach_exit_reason_to_dim(
    dim_dict: dict[str, Any], run_exit_reason: str | None,
) -> dict[str, Any]:
    """Add ``exitReason`` to a serialized dimension dict.

    Preference order: per-dim exit_reason (if present on the dim) wins over
    the run-level value. Either way, the chosen reason is exposed to the UI
    as ``exitReason``. Falls back to no key when both are absent (legacy).
    """
    per_dim = dim_dict.get("exit_reason") or dim_dict.get("exitReason")
    chosen = per_dim or run_exit_reason
    if chosen is None:
        # Drop the snake_case key if present, to keep the response clean.
        if "exit_reason" in dim_dict:
            out = dict(dim_dict)
            out.pop("exit_reason", None)
            return out
        return dim_dict
    out = dict(dim_dict)
    out.pop("exit_reason", None)
    out["exitReason"] = chosen
    return out


def _attach_dismissed_count_to_dim(
    dim_dict: dict[str, Any], dismissed_counts: dict[str, int],
    suppressed_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Add ``dismissedCount`` / ``suppressedCount`` to a dimension dict when > 0.

    Both explain the gap between "what the scan found" and "what the view
    shows". ``dismissedCount`` covers the dismissed filter alone;
    ``suppressedCount`` covers dismissals *and* deletions, so it is the total
    the UI reports. They differ sharply on projects with a triage history:
    deletions suppress a whole principle across a file and accumulate over
    many runs, so a scan can re-find several times what the report displays.
    Omitted when nothing was filtered, mirroring the exitReason convention.
    """
    key = dim_dict.get("dimension") or ""
    out = dim_dict
    count = dismissed_counts.get(key, 0)
    if count > 0:
        out = {**out, "dismissedCount": count}
    total = (suppressed_counts or {}).get(key, 0)
    if total > 0:
        out = {**out, "suppressedCount": total}
    return out


def _slim_history_dim(dim: DimensionResult) -> dict[str, Any]:
    """Serialize a history-context dimension without its finding bodies.

    The previousByDimension / stalePreviousByDimension / staleDimensions keys
    exist to carry scores, grades, and provenance (run id, dates) for trend
    context; the UI reads only the scalar fields inlined on each selected-run
    dimension (previousScore, trend, stale, fromRunId). No consumer reads the
    violations/compliance arrays from these keys, yet on large projects they
    dominated the payload: for a 201-run project, an old run's dashboard was
    19.9 MB of which these three keys carried 18.6 MB of finding bodies.
    Totals keep the counts; only the bodies are dropped.
    """
    return to_camel_dict(replace(dim, violations=[], compliance=[]))


def _build_dashboard_result(
    project: str,
    runs: list[RunInfo],
    selected_run: RunInfo,
    payload: _DashboardPayload,
    *,
    exit_reason: str | None = None,
    dismissed_counts: dict[str, int] | None = None,
    suppressed_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Assemble the final dashboard response dict from pre-computed parts."""
    dim_dicts = [
        _attach_dismissed_count_to_dim(
            _attach_exit_reason_to_dim(to_camel_dict(d), exit_reason),
            dismissed_counts or {},
            suppressed_counts or {},
        )
        for d in payload.dimensions_with_trend
    ]
    return {
        "project": project,
        "availableRuns": [
            {"runId": item.run_id, "dateISO": item.date_iso, "dateLabel": item.date_label, "status": item.status}
            for item in runs
        ],
        "selectedRun": {
            "runId": selected_run.run_id,
            "dateISO": selected_run.date_iso,
            "dateLabel": selected_run.date_label,
            "exitReason": exit_reason,
        },
        "summary": {
            **to_camel_dict(payload.selected_summary),
            "dateISO": selected_run.date_iso,
            "dateLabel": selected_run.date_label,
        },
        "trend": payload.trend,
        "dimensions": dim_dicts,
        "previousByDimension": {k: _slim_history_dim(v) for k, v in payload.previous_by_dimension.items()},
        "stalePreviousByDimension": {k: _slim_history_dim(v) for k, v in payload.stale_previous_by_dimension.items()},
        "staleDimensions": [_slim_history_dim(d) for d in payload.stale_dimensions],
    }
