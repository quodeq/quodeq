"""Accumulated (cross-run) overview tool — the default dashboard data.

The run-scoped tools in ``_read_tools`` read a single ``run_dir``. On the
overview the user sees the *accumulated* view aggregated across recent runs,
so there is no single run to read. ``get_overview`` fills that gap by calling
``services._fs_reports.get_accumulated`` (assistant→services is a legal
import) and trimming the payload to what a chat needs.
"""
from __future__ import annotations

from quodeq.assistant.tools._context import ToolContext
from quodeq.assistant.tools._registry import ToolError, ToolRegistry, ToolSpec
from quodeq.services import _fs_reports
from quodeq.services.scoring import rescore_accumulated


def _get_overview(ctx: ToolContext, as_of: str | None = None) -> dict:
    if ctx.reports_dir is None or ctx.project_id is None:
        raise ToolError(
            "no project selected for this session; overview data unavailable. "
            "Call get_context to confirm scope, then ask the user to open a "
            "project overview."
        )
    payload = _fs_reports.get_accumulated(str(ctx.reports_dir), ctx.project_id, as_of)
    if payload is None:
        raise ToolError(f"no accumulated data for project: {ctx.project_id}")
    # Project-wide dismiss/delete rescore: the raw accumulated payload keeps
    # the baked pre-triage scores, so without this the assistant quotes lower
    # scores than the Overview shows for the same project (no-op when the
    # project has no active dismissals/deletions).
    payload = rescore_accumulated(payload, ctx.reports_dir, ctx.project_id)
    dimensions = [
        {
            "dimension": d.get("dimension"),
            "score": d.get("overallScore"),
            "grade": d.get("overallGrade"),
            "trend": d.get("trend"),
        }
        for d in payload.get("dimensions", [])
    ]
    summary = payload.get("summary", {}) or {}
    return {
        "project": payload.get("project"),
        "dimensions": dimensions,
        "summary": {
            "overallGrade": summary.get("overallGrade"),
            "numericAverage": summary.get("numericAverage"),
            "totalViolations": summary.get("totalViolations"),
            "dimensionCount": summary.get("dimensionCount"),
            "severity": summary.get("severity"),
        },
    }


def register_overview_tools(registry: ToolRegistry, ctx: ToolContext) -> None:
    registry.register(ToolSpec(
        "get_overview",
        "Get accumulated dimension scores and grades aggregated across the "
        "project's recent runs (the overview/dashboard view). Use this when no "
        "specific run is selected. Call get_context first if unsure whether "
        "overviewAvailable is true. Optional 'as_of' is a run id: accumulate "
        "only that run and older ones.",
        {"type": "object", "properties": {
            "as_of": {"type": "string"},
        }},
        lambda **kw: _get_overview(ctx, **kw)))
