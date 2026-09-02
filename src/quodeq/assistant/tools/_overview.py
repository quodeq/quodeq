"""Accumulated (cross-run) overview tool — the default dashboard data.

The run-scoped tools in ``_read_tools`` read a single ``run_dir``. On the
overview the user sees the *accumulated* view aggregated across recent runs,
so there is no single run to read. ``get_overview`` fills that gap by calling
``quodeq.services.get_accumulated`` (assistant→services is a legal import)
and trimming the payload to what a chat needs.
"""
from __future__ import annotations

from quodeq.assistant.tools._context import ToolContext
from quodeq.assistant.tools._registry import ToolError, ToolRegistry, ToolSpec
from quodeq.core.standards.visibility import partition_entries_visible
from quodeq.services import get_accumulated
from quodeq.services.scoring import rescore_accumulated

# Severity buckets recomputed for the filtered summary. Unknown/missing
# severities are ignored rather than added as a fourth bucket.
_SEVERITY_BUCKETS = ("critical", "major", "minor")


def _build_filtered_summary(payload: dict, kept: list[dict], hidden: list) -> dict:
    """Build the overview summary dict, recomputed when standards are hidden.

    When nothing is hidden, the baked summary fields are passed through.
    When some are hidden, overallGrade/numericAverage are omitted and counts
    are recomputed from *kept* only.
    """
    summary = payload.get("summary", {}) or {}
    if not hidden:
        return {
            "overallGrade": summary.get("overallGrade"),
            "numericAverage": summary.get("numericAverage"),
            "totalViolations": summary.get("totalViolations"),
            "dimensionCount": summary.get("dimensionCount"),
            "severity": summary.get("severity"),
        }
    # overallGrade/numericAverage are deliberately absent. The Overview
    # derives them from the filtered TREND in the browser
    # (ui/src/utils/scoreFiltering.js), not from these dimensions, so any
    # value computed here could contradict the number on screen -- the
    # divergence this filtering exists to prevent. Counts are exact, so
    # they are recomputed rather than dropped.
    severity = {bucket: 0 for bucket in _SEVERITY_BUCKETS}
    total = 0
    for d in kept:
        for v in (d.get("violations") or []):
            total += 1
            level = (v.get("severity") or "").lower()
            if level in severity:
                severity[level] += 1
    return {
        "totalViolations": total,
        "dimensionCount": len(kept),
        "severity": severity,
        "note": ("overall grade and average omitted: they cover all "
                 "standards, including the ones hidden from this project's "
                 "dashboard. Quote the per-dimension scores instead, or "
                 "point the user at the Overview."),
    }


def _get_overview(ctx: ToolContext, as_of: str | None = None) -> dict:
    if ctx.reports_dir is None or ctx.project_id is None:
        raise ToolError(
            "no project selected for this session; overview data unavailable. "
            "Call get_context to confirm scope, then ask the user to open a "
            "project overview."
        )
    payload = get_accumulated(str(ctx.reports_dir), ctx.project_id, as_of)
    if payload is None:
        raise ToolError(f"no accumulated data for project: {ctx.project_id}")
    # Project-wide dismiss/delete rescore: the raw accumulated payload keeps
    # the baked pre-triage scores, so without this the assistant quotes lower
    # scores than the Overview shows for the same project (no-op when the
    # project has no active dismissals/deletions).
    payload = rescore_accumulated(payload, ctx.reports_dir, ctx.project_id)
    raw_dims = payload.get("dimensions", []) or []
    # Shared with _read_tools._visible_only: one implementation of "what
    # counts as hidden" for every read surface.
    kept, hidden = partition_entries_visible(raw_dims, ctx.visible_standard_ids)
    dimensions = [
        {
            "dimension": d.get("dimension"),
            "score": d.get("overallScore"),
            "grade": d.get("overallGrade"),
            "trend": d.get("trend"),
        }
        for d in kept
    ]
    out_summary = _build_filtered_summary(payload, kept, hidden)
    return {
        "project": payload.get("project"),
        "dimensions": dimensions,
        "summary": out_summary,
        "hiddenStandardIds": hidden,
    }


def register_overview_tools(registry: ToolRegistry, ctx: ToolContext) -> None:
    registry.register(ToolSpec(
        "get_overview",
        "Get accumulated dimension scores and grades aggregated across the "
        "project's recent runs (the overview/dashboard view). Use this when no "
        "specific run is selected. Call get_context first if unsure whether "
        "overviewAvailable is true. Optional 'as_of' is a run id: accumulate "
        "only that run and older ones. Covers only the standards visible on "
        "this project's dashboard; any others are named in hiddenStandardIds. "
        "When standards are hidden the summary omits the overall grade and "
        "average on purpose -- do not compute your own from the dimension "
        "scores.",
        {"type": "object", "properties": {
            "as_of": {"type": "string"},
        }},
        lambda **kw: _get_overview(ctx, **kw)))
