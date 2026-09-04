"""Read-only tools over evaluation artifacts and the standards library."""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from quodeq.assistant.tools._context import ToolContext
from quodeq.assistant.tools._read_tools_scope import (
    _accumulated_dims,
    _findings_repo,
    _has_run,
    _no_scope_error,
    _require_run,
    _scored_run_dims,
    finding_keys_in_scope,  # noqa: F401 - re-export (assistant/tools import, external tests)
)
from quodeq.assistant.tools._read_tools_violations import (
    _available_names,
    _get_violations,
    _hidden_ids,
    _trim_violation,
    _visible_only,
)
from quodeq.assistant.tools._registry import ToolError, ToolRegistry, ToolSpec
from quodeq.core.standards.visibility import partition_visible
from quodeq.data.fs.report_parser.finding_details import (
    iter_eval_reports,
    read_eval_report,
)
from quodeq.data.ports.findings import FindingsRepository
# Imported for its module identity, not called directly here: tests patch
# `quodeq.assistant.tools._read_tools._fs_reports.get_accumulated`, which
# mutates the shared `_fs_reports` module object that
# `_read_tools_scope._accumulated_dims` actually calls through.
from quodeq.services import _fs_reports  # noqa: F401 - re-export (patch target)
from quodeq.services.standards import StandardsService

# Dimension ids are simple slugs. The tool-call `dimension` argument is
# model-controlled text used to build a file path, so anything outside this
# charset (path separators, dots, absolute paths) is rejected outright.
_DIMENSION_RE = re.compile(r"[a-z0-9_-]+")
# Cap violations embedded in a full report so a single get_report stays small.
_REPORT_VIOLATION_CAP = 40


def _validate_dimension(dimension: str) -> str:
    if not isinstance(dimension, str) or not _DIMENSION_RE.fullmatch(dimension):
        raise ToolError(f"invalid dimension: {dimension!r}")
    return dimension


def default_findings_repo_factory(run_dir: Path) -> FindingsRepository:
    """Composition fallback: the concrete SQLite findings repository.

    Real composition roots (``api._assistant_helpers.build_tool_context``,
    the MCP server) pass ``ToolContext.findings_repo_factory`` explicitly;
    this lazy default keeps directly-constructed contexts working without
    coupling the context module — or this module's import time — to SQLite.
    """
    from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository  # noqa: PLC0415
    return SqliteFindingsRepository(run_dir)


def _raw_run_dims(eval_dir: Path) -> list[dict]:
    """A run's evaluation reports as dicts, each guaranteed a ``dimension``.

    Mirrors the pre-filtering fallback ``data.get("dimension", path.stem)``: a
    report that omits the field is named after its file rather than dropped.
    """
    out: list[dict] = []
    for dimension, data in iter_eval_reports(eval_dir):
        data.setdefault("dimension", dimension)
        out.append(data)
    return out


def _search_findings(ctx: ToolContext, query: str, limit: int = 20) -> dict:
    run_dir = _require_run(ctx)
    repo = _findings_repo(ctx, run_dir)
    # Hidden dims must be known BEFORE the query runs, so the exclusion can be
    # pushed into SQL ahead of LIMIT (see SqliteFindingsRepository.search).
    # Filtering the returned rows afterward is not equivalent: rows are
    # ordered by insertion order, evaluators insert per dimension in batches,
    # and enough hidden-dimension rows ahead of the visible ones can exhaust
    # the whole limit window, returning zero results even though visible ones
    # exist. Sourced from every dimension in the run's DB (not from the
    # query's hits) so a dimension whose rows never come back from SQL is
    # still reported as withheld.
    hidden = _hidden_ids(ctx, list(repo.count_by_dimension()))
    hits = repo.search(query, limit=max(1, min(int(limit), 50)),
                        exclude_dimensions=hidden or None)
    # Model-facing key is "requirement"; the Finding attribute is `req`
    # (see data/sqlite/_row_mappers.py row_to_finding).
    rows = [
        {"dimension": f.dimension, "requirement": f.req, "severity": f.severity,
         "file": f.file, "line": f.line, "reason": f.reason, "snippet": f.snippet}
        for f in hits
    ]
    return {"findings": rows, "hiddenStandardIds": hidden}


def _get_scores(ctx: ToolContext) -> dict:
    # A specific run selected → that run's dims. Otherwise the accumulated
    # (per-dimension-latest) scores — the default dashboard/overview view.
    if _has_run(ctx):
        eval_dir = ctx.run_dir / "evaluation"
        if not eval_dir.is_dir():
            raise ToolError("no evaluation reports in this run")
        scored = _scored_run_dims(ctx)
        if scored is None:
            scored = _raw_run_dims(eval_dir)
        kept, hidden = _visible_only(ctx, scored)
        return {
            "scores": {d["dimension"]: {
                "score": d.get("overallScore"), "grade": d.get("overallGrade"),
            } for d in kept if d.get("dimension")},
            "hiddenStandardIds": hidden,
        }
    dims = _accumulated_dims(ctx)
    if dims is None:
        raise _no_scope_error()
    kept, hidden = _visible_only(ctx, dims)
    return {
        "scores": {d.get("dimension"): {
            "score": d.get("overallScore"), "grade": d.get("overallGrade"),
            "fromRun": d.get("fromRunId"),
        } for d in kept if d.get("dimension")},
        "hiddenStandardIds": hidden,
    }


def _get_report_from_run(ctx: ToolContext, dimension: str) -> dict:
    data = read_eval_report(ctx.run_dir / "evaluation", dimension)
    if data is None:
        raise ToolError(f"no report for dimension: {dimension}")
    out = {k: data.get(k) for k in
           ("dimension", "overallScore", "overallGrade", "principles",
            "totals", "coveragePct")}
    viols = data.get("violations") or []
    scored = _scored_run_dims(ctx)
    if scored is not None:
        entry = next((d for d in scored if d.get("dimension") == dimension), None)
        if entry is not None:
            # Swap in the dismiss-adjusted fields; keep the raw report's
            # shape (coveragePct etc.) untouched. Principles get the same
            # "name" normalization as the accumulated branch below.
            out["overallScore"] = entry.get("overallScore")
            out["overallGrade"] = entry.get("overallGrade")
            out["principles"] = [{**p, "name": p.get("name") or p.get("principle")}
                                 for p in (entry.get("principles") or [])]
            out["totals"] = entry.get("totals")
            viols = entry.get("violations") or []
    out["violations"] = [_trim_violation(v) for v in viols[:_REPORT_VIOLATION_CAP]]
    return out


def _get_report_from_accumulated(ctx: ToolContext, dimension: str) -> dict:
    dims = _accumulated_dims(ctx)
    if dims is None:
        raise _no_scope_error()
    entry = next((d for d in dims if d.get("dimension") == dimension), None)
    if entry is None:
        avail = _available_names(ctx, dims)
        raise ToolError(
            f"no report for dimension: {dimension}. Available: {avail or '(none)'}")
    viols = entry.get("violations") or []
    # Run-scoped principles are keyed "name"; the accumulated (PrincipleGrade)
    # shape keys the same thing "principle" -- normalize so callers can always
    # read `name` regardless of scope, without dropping any existing keys.
    principles = [{**p, "name": p.get("name") or p.get("principle")}
                  for p in (entry.get("principles") or [])]
    return {
        "dimension": entry.get("dimension"),
        "overallScore": entry.get("overallScore"),
        "overallGrade": entry.get("overallGrade"),
        "principles": principles,
        "totals": entry.get("totals"),
        # No coveragePct key here: DimensionResult (the accumulated payload)
        # has no coverage field, so this was always None -- omit rather than
        # return a key that's permanently null.
        # The accumulated view picks each dimension's latest run independently;
        # expose which run this dimension's data came from.
        "fromRun": entry.get("fromRunId"),
        "violations": [_trim_violation(v) for v in viols[:_REPORT_VIOLATION_CAP]],
    }


def _get_report(ctx: ToolContext, dimension: str) -> dict:
    _validate_dimension(dimension)
    if _has_run(ctx):
        return _get_report_from_run(ctx, dimension)
    return _get_report_from_accumulated(ctx, dimension)


def _service(ctx: ToolContext) -> StandardsService:
    return StandardsService(ctx.evaluators_dir, ctx.compiled_dir, ctx.dimensions_file)


def _list_standards(ctx: ToolContext, include_hidden: bool = False) -> dict:
    metas = _service(ctx).list_standards()
    shown, hidden = partition_visible([m.id for m in metas], ctx.visible_standard_ids)
    keep = set(shown) if not include_hidden else {m.id for m in metas}
    return {
        "standards": [dataclasses.asdict(m) for m in metas if m.id in keep],
        "hiddenStandardIds": hidden,
    }


def _get_standard(ctx: ToolContext, standard_id: str) -> dict:
    try:
        detail = _service(ctx).get_standard(standard_id)
    except (KeyError, FileNotFoundError, ValueError) as exc:
        raise ToolError(f"standard not found: {standard_id}") from exc
    return dataclasses.asdict(detail)


def _register_findings_tools(registry: ToolRegistry, ctx: ToolContext) -> None:
    registry.register(ToolSpec(
        "search_findings",
        "Full-text search the selected run's findings. Requires a selected run; "
        "call get_context first if unsure. In overview scope, use get_violations "
        "or get_report instead.",
        {"type": "object", "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        }, "required": ["query"]},
        lambda **kw: _search_findings(ctx, **kw)))
    registry.register(ToolSpec(
        "get_violations",
        "List violations for a dimension (or all dimensions if omitted), "
        "severity-sorted with per-principle counts. Uses the selected run if "
        "one is selected, otherwise the accumulated (per-dimension-latest) view.",
        {"type": "object", "properties": {
            "dimension": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        }},
        lambda **kw: _get_violations(ctx, **kw)))


def _register_score_tools(registry: ToolRegistry, ctx: ToolContext) -> None:
    registry.register(ToolSpec(
        "get_scores",
        "Get all dimension scores and grades, as {scores: {dimension: "
        "{score, grade}}, hiddenStandardIds: [...]}. Uses the selected run if "
        "one is selected, otherwise the accumulated view (each dimension's "
        "latest run, aggregated — the default dashboard data). scores omits "
        "any dimension the user has hidden; those ids are named in "
        "hiddenStandardIds.",
        {"type": "object", "properties": {}},
        lambda **kw: _get_scores(ctx, **kw)))
    registry.register(ToolSpec(
        "get_report",
        "Get the full report for one dimension: principles (score/grade) and "
        "violations. Uses the selected run if one is selected, otherwise that "
        "dimension's latest run from the accumulated view.",
        {"type": "object", "properties": {"dimension": {"type": "string"}},
         "required": ["dimension"]},
        lambda **kw: _get_report(ctx, **kw)))


def _register_standards_tools(registry: ToolRegistry, ctx: ToolContext) -> None:
    registry.register(ToolSpec(
        "list_standards",
        "List the standards this project evaluates. Returns only the standards "
        "the user has selected as visible; any others are named in "
        "hiddenStandardIds. Pass include_hidden=true, or call "
        "get_standard(standard_id), when the user explicitly asks about a "
        "hidden standard.",
        {"type": "object", "properties": {
            "include_hidden": {"type": "boolean"},
        }},
        lambda **kw: _list_standards(ctx, **kw)))
    registry.register(ToolSpec(
        "get_standard", "Get one standard's full principles and requirements.",
        {"type": "object", "properties": {"standard_id": {"type": "string"}},
         "required": ["standard_id"]},
        lambda **kw: _get_standard(ctx, **kw)))


def register_read_tools(registry: ToolRegistry, ctx: ToolContext) -> None:
    _register_findings_tools(registry, ctx)
    _register_score_tools(registry, ctx)
    _register_standards_tools(registry, ctx)
