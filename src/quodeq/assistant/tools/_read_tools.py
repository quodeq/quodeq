"""Read-only tools over evaluation artifacts and the standards library."""
from __future__ import annotations

import dataclasses
import json

from quodeq.assistant.tools._context import ToolContext
from quodeq.assistant.tools._registry import ToolError, ToolRegistry, ToolSpec
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository
from quodeq.services.standards import StandardsService

# NOTE: deviates from the task brief, which listed "requirement" here. The
# `Finding` dataclass (src/quodeq/core/types/finding.py) has no `requirement`
# attribute -- the requirement id is stored as `req` (see
# data/sqlite/_row_mappers.py row_to_finding: `req=row.get("requirement")`).
# Using "requirement" would raise AttributeError on every call.
_FINDING_FIELDS = ("dimension", "req", "severity", "file", "line",
                   "reason", "snippet")


def _require_run(ctx: ToolContext):
    if ctx.run_dir is None or not ctx.run_dir.exists():
        raise ToolError("no run selected for this session")
    return ctx.run_dir


def _search_findings(ctx: ToolContext, query: str, limit: int = 20) -> dict:
    run_dir = _require_run(ctx)
    hits = SqliteFindingsRepository(run_dir).search(query, limit=min(int(limit), 50))
    return {"findings": [
        {k: getattr(f, k) for k in _FINDING_FIELDS} for f in hits
    ]}


def _get_scores(ctx: ToolContext) -> dict:
    run_dir = _require_run(ctx)
    eval_dir = run_dir / "evaluation"
    if not eval_dir.is_dir():
        raise ToolError("no evaluation reports in this run")
    out = {}
    for path in sorted(eval_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        out[data.get("dimension", path.stem)] = {
            "score": data.get("overallScore"), "grade": data.get("overallGrade"),
        }
    return out


def _get_report(ctx: ToolContext, dimension: str) -> dict:
    run_dir = _require_run(ctx)
    path = run_dir / "evaluation" / f"{dimension}.json"
    if not path.is_file():
        raise ToolError(f"no report for dimension: {dimension}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: data.get(k) for k in
            ("dimension", "overallScore", "overallGrade", "principles",
             "totals", "coveragePct")}


def _service(ctx: ToolContext) -> StandardsService:
    return StandardsService(ctx.evaluators_dir, ctx.compiled_dir, ctx.dimensions_file)


def _list_standards(ctx: ToolContext) -> dict:
    metas = _service(ctx).list_standards()
    return {"standards": [dataclasses.asdict(m) for m in metas]}


def _get_standard(ctx: ToolContext, standard_id: str) -> dict:
    try:
        detail = _service(ctx).get_standard(standard_id)
    except (KeyError, FileNotFoundError, ValueError) as exc:
        raise ToolError(f"standard not found: {standard_id}") from exc
    return dataclasses.asdict(detail)


def register_read_tools(registry: ToolRegistry, ctx: ToolContext) -> None:
    registry.register(ToolSpec(
        "search_findings", "Full-text search the selected run's findings.",
        {"type": "object", "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        }, "required": ["query"]},
        lambda **kw: _search_findings(ctx, **kw)))
    registry.register(ToolSpec(
        "get_scores", "Get all dimension scores and grades for the selected run.",
        {"type": "object", "properties": {}},
        lambda **kw: _get_scores(ctx, **kw)))
    registry.register(ToolSpec(
        "get_report", "Get the full report for one dimension of the selected run.",
        {"type": "object", "properties": {"dimension": {"type": "string"}},
         "required": ["dimension"]},
        lambda **kw: _get_report(ctx, **kw)))
    registry.register(ToolSpec(
        "list_standards", "List all built-in and custom standards.",
        {"type": "object", "properties": {}},
        lambda **kw: _list_standards(ctx, **kw)))
    registry.register(ToolSpec(
        "get_standard", "Get one standard's full principles and requirements.",
        {"type": "object", "properties": {"standard_id": {"type": "string"}},
         "required": ["standard_id"]},
        lambda **kw: _get_standard(ctx, **kw)))
