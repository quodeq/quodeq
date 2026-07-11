"""Read-only tools over evaluation artifacts and the standards library."""
from __future__ import annotations

import dataclasses
import json

from quodeq.assistant.tools._context import ToolContext
from quodeq.assistant.tools._registry import ToolError, ToolRegistry, ToolSpec
from quodeq.core.types import to_camel_dict
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository
from quodeq.services import _fs_reports
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services.scoring import rescore_accumulated, scored_run_dimensions
from quodeq.services.standards import StandardsService

def _require_run(ctx: ToolContext):
    if ctx.run_dir is None or not ctx.run_dir.exists():
        raise ToolError(
            "no run selected for this session. Call get_context to confirm "
            "scope. For project overview sessions, use get_violations or "
            "get_report instead of search_findings.")
    return ctx.run_dir


def _has_run(ctx: ToolContext) -> bool:
    """A specific run was selected (vs. the accumulated overview scope)."""
    return ctx.run_dir is not None and ctx.run_dir.exists()


def _accumulated_dims(ctx: ToolContext, *, rescored: bool = True) -> list[dict] | None:
    """Per-dimension-latest composition (the dashboard/overview data).

    Each entry is one dimension sourced from ITS OWN latest run — so the set
    can span several runs, exactly like the dashboard. Carries overallScore/
    Grade, principles, violations and the source run (``fromRunId``). Returns
    None when the session has no project scope.

    By default the project-wide dismiss/delete rescore is applied so the
    scores the model quotes match the Overview (``get_project_scores``) — the
    raw ``compute_accumulated`` payload filters dismissed violations from the
    lists but leaves the baked pre-triage scores untouched.
    ``rescored=False`` returns that raw payload; it exists for
    ``finding_keys_in_scope``, which must keep seeing every finding a
    dismiss/verify key could legitimately reference.
    """
    if ctx.reports_dir is None or ctx.project_id is None:
        return None
    payload = _fs_reports.get_accumulated(str(ctx.reports_dir), ctx.project_id, None)
    if payload is None:
        return None
    if rescored:
        payload = rescore_accumulated(payload, ctx.reports_dir, ctx.project_id)
    return payload.get("dimensions", []) or []


def _scored_run_dims(ctx: ToolContext) -> list[dict] | None:
    """The selected run's dimensions with the project-wide dismiss/delete
    rescore applied, as camelCase dicts.

    Routes through ``scored_run_dimensions`` — the same seam the explorer,
    dashboard and dimension detail read through — so the assistant quotes the
    same dismiss-adjusted score as every UI surface. Returns None when the
    project has no active dismissals/deletions (callers keep the raw eval-JSON
    read: byte-identical output, no parse round-trip) or when the run's
    location can't be resolved against the reports tree (fail-open: raw data
    beats erroring the chat turn).
    """
    project_dir = ctx.run_dir.parent
    try:
        if not dismissed_keys(project_dir) and not deleted_keys(project_dir):
            return None
        dims = scored_run_dimensions(project_dir.parent, project_dir.name, ctx.run_dir.name)
    except Exception:  # noqa: BLE001 - unresolvable layout: serve raw, not a ToolError
        return None
    return [to_camel_dict(d) for d in dims]


def _no_scope_error() -> ToolError:
    return ToolError(
        "no project or run scope for this session. Call get_context to confirm "
        "scope, then ask the user to open a project overview or select a run.")


# Trimmed violation shape shared by get_report and get_violations. We keep only
# the fields that let the model locate and explain an issue and DROP the large
# `snippet`/`context` blobs so a report full of violations stays within a sane
# context budget. Use search_findings when the model needs the code snippet.
_VIOLATION_FIELDS = ("principle", "file", "line", "severity", "title", "reason")
# Cap violations embedded in a full report so a single get_report stays small.
_REPORT_VIOLATION_CAP = 40
# get_violations paging limits.
_VIOLATIONS_DEFAULT_LIMIT = 40
_VIOLATIONS_MAX_LIMIT = 100
# Severity ordering (critical/major first). Unknown severities sort last.
_SEVERITY_RANK = {
    "critical": 0, "blocker": 0, "high": 1, "major": 1,
    "moderate": 2, "medium": 2, "minor": 3, "low": 3, "info": 4, "trivial": 4,
}


def _principle_of(v: dict):
    # Run-scoped eval JSON keys the principle as "principle"; the accumulated
    # payload (serialized Finding) keys it as "practiceId". Accept either so
    # one trim/sort works for both scopes.
    return v.get("principle") or v.get("practiceId")


def _requirement_of(v: dict) -> str:
    # The requirement id (Finding.req) is the FIRST element of the (req, file,
    # line) identity that dismiss/verify and the suppression filter key on.
    # Run-scoped eval JSON and the accumulated serialized-Finding payload both
    # key it as "req"; accept "requirement" too for any producer that already
    # renamed it. Often absent (req is optional; practiceId is the guaranteed
    # identity), so it is normalized to "" rather than None so it round-trips
    # as a valid dismiss key.
    return str(v.get("req") or v.get("requirement") or "")


def _coerce_line(line) -> int:
    # dismiss keys store line as int; Finding.line is typed int|str|None. Coerce
    # so a string line ("5") still matches a stored int line (5).
    try:
        return int(line)
    except (TypeError, ValueError):
        return 0


def _trim_violation(v: dict) -> dict:
    out = {k: v.get(k) for k in _VIOLATION_FIELDS}
    out["principle"] = _principle_of(v)
    # Expose the requirement id so the model can form a correct dismiss/verify
    # key. Without it, get_report/get_violations only surfaced `principle`, and
    # a dismiss drafted from that data carried a wrong/empty req that never
    # matched the finding on the suppression read path (silent no-op).
    out["requirement"] = _requirement_of(v)
    return out


def finding_keys_in_scope(ctx: ToolContext) -> set[tuple]:
    """Every ``(req, file, line)`` identity the model can see in this scope.

    Used to validate a dismiss/verify draft against a real finding before it is
    recorded, so the model cannot persist an action whose key matches nothing.
    Unions EVERY source a read tool can surface, so the check never falsely
    rejects a finding the model legitimately saw:

    - run scope: the UNCAPPED eval-JSON violations (get_report/get_violations)
      AND the SQL findings table (search_findings) -- the two can drift, and a
      finding present in only one must still be dismissable.
    - overview scope: the accumulated per-dimension-latest violations.

    Best-effort: each source is guarded independently so one unreadable source
    (e.g. a missing eval dir or a corrupt evaluation.db) still leaves the others
    usable, and a wholly unreadable scope surfaces as "no matching finding"
    rather than a stack trace.
    """
    keys: set[tuple] = set()

    def _add(v: dict) -> None:
        keys.add((_requirement_of(v), str(v.get("file") or ""), _coerce_line(v.get("line"))))

    if _has_run(ctx):
        eval_dir = ctx.run_dir / "evaluation"
        if eval_dir.is_dir():
            # Parse each dimension file INDEPENDENTLY: one corrupt/truncated file
            # (a known failure mode of deadline-cut runs) must drop only its own
            # findings, not discard every healthy dimension's keys.
            for p in sorted(eval_dir.glob("*.json")):
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                for v in (data.get("violations") or []):
                    _add(v)
        # SQL findings (the search_findings source). Read only an EXISTING db so
        # a read-only draft never creates evaluation.db or kicks a projection on
        # a run that has none -- when there is no db there are no SQL findings to
        # miss anyway.
        if (ctx.run_dir / "evaluation.db").is_file():
            try:
                for f in SqliteFindingsRepository(ctx.run_dir).list_all():
                    keys.add((str(f.req or ""), str(f.file or ""), _coerce_line(f.line)))
            except Exception:  # noqa: BLE001 - a corrupt db must not block the read
                pass
    else:
        try:
            # rescored=False: the identity check must keep seeing every finding
            # a dismiss/verify key could reference, including already-dismissed
            # ones (idempotent re-dismiss / verify must still match).
            for d in (_accumulated_dims(ctx, rescored=False) or []):
                for v in (d.get("violations") or []):
                    _add(v)
        except (ToolError, OSError, ValueError):
            pass
    return keys


def _severity_key(v: dict):
    sev = (v.get("severity") or "").lower()
    return (_SEVERITY_RANK.get(sev, 99), _principle_of(v) or "")


def _search_findings(ctx: ToolContext, query: str, limit: int = 20) -> dict:
    run_dir = _require_run(ctx)
    hits = SqliteFindingsRepository(run_dir).search(query, limit=max(1, min(int(limit), 50)))
    # Model-facing key is "requirement"; the Finding attribute is `req`
    # (see data/sqlite/_row_mappers.py row_to_finding).
    return {"findings": [
        {"dimension": f.dimension, "requirement": f.req, "severity": f.severity,
         "file": f.file, "line": f.line, "reason": f.reason, "snippet": f.snippet}
        for f in hits
    ]}


def _get_scores(ctx: ToolContext) -> dict:
    # A specific run selected → that run's dims. Otherwise the accumulated
    # (per-dimension-latest) scores — the default dashboard/overview view.
    if _has_run(ctx):
        eval_dir = ctx.run_dir / "evaluation"
        if not eval_dir.is_dir():
            raise ToolError("no evaluation reports in this run")
        scored = _scored_run_dims(ctx)
        if scored is not None:
            return {d["dimension"]: {
                "score": d.get("overallScore"), "grade": d.get("overallGrade"),
            } for d in scored if d.get("dimension")}
        out = {}
        for path in sorted(eval_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            out[data.get("dimension", path.stem)] = {
                "score": data.get("overallScore"), "grade": data.get("overallGrade"),
            }
        return out
    dims = _accumulated_dims(ctx)
    if dims is None:
        raise _no_scope_error()
    return {d.get("dimension"): {
        "score": d.get("overallScore"), "grade": d.get("overallGrade"),
        "fromRun": d.get("fromRunId"),
    } for d in dims if d.get("dimension")}


def _get_report(ctx: ToolContext, dimension: str) -> dict:
    if _has_run(ctx):
        path = ctx.run_dir / "evaluation" / f"{dimension}.json"
        if not path.is_file():
            raise ToolError(f"no report for dimension: {dimension}")
        data = json.loads(path.read_text(encoding="utf-8"))
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
    dims = _accumulated_dims(ctx)
    if dims is None:
        raise _no_scope_error()
    entry = next((d for d in dims if d.get("dimension") == dimension), None)
    if entry is None:
        avail = ", ".join(sorted(d.get("dimension") for d in dims if d.get("dimension")))
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


def _get_violations(ctx: ToolContext, dimension: str | None = None,
                    limit: int = _VIOLATIONS_DEFAULT_LIMIT) -> dict:
    limit = max(1, min(int(limit), _VIOLATIONS_MAX_LIMIT))
    if _has_run(ctx):
        raw, dim_out = _violations_from_run(ctx, dimension)
    else:
        raw, dim_out = _violations_from_accumulated(ctx, dimension)

    # by_principle counts reflect ALL violations so "worst principle" stays
    # accurate even when the returned list is capped by `limit`.
    by_principle: dict[str, int] = {}
    for v in raw:
        key = _principle_of(v) or "(unknown)"
        by_principle[key] = by_principle.get(key, 0) + 1

    ordered = sorted(raw, key=_severity_key)
    trimmed = [_trim_violation(v) for v in ordered[:limit]]
    return {"dimension": dim_out, "count": len(raw),
            "violations": trimmed, "by_principle": by_principle}


def _violations_from_run(ctx: ToolContext, dimension: str | None):
    eval_dir = ctx.run_dir / "evaluation"
    if dimension:
        path = eval_dir / f"{dimension}.json"
        if not path.is_file():
            raise ToolError(
                f"no report for dimension: {dimension} in this run. "
                "Check get_scores for available dimensions, or get_overview "
                "for accumulated scores across runs.")
        scored = _scored_run_dims(ctx)
        if scored is not None:
            entry = next((d for d in scored if d.get("dimension") == dimension), None)
            if entry is not None:
                return entry.get("violations") or [], dimension
        return json.loads(path.read_text(encoding="utf-8")).get("violations") or [], dimension
    if not eval_dir.is_dir():
        raise ToolError(
            "no evaluation reports in this run. Try get_overview for "
            "accumulated scores across runs.")
    scored = _scored_run_dims(ctx)
    if scored is not None:
        return [v for d in scored for v in (d.get("violations") or [])], None
    raw: list = []
    for p in sorted(eval_dir.glob("*.json")):
        raw.extend(json.loads(p.read_text(encoding="utf-8")).get("violations") or [])
    return raw, None


def _violations_from_accumulated(ctx: ToolContext, dimension: str | None):
    dims = _accumulated_dims(ctx)
    if dims is None:
        raise _no_scope_error()
    if dimension:
        entry = next((d for d in dims if d.get("dimension") == dimension), None)
        if entry is None:
            avail = ", ".join(sorted(d.get("dimension") for d in dims if d.get("dimension")))
            raise ToolError(
                f"no report for dimension: {dimension}. Available: "
                f"{avail or '(none)'}. Or try get_overview for accumulated scores.")
        return entry.get("violations") or [], dimension
    raw: list = []
    for d in dims:
        raw.extend(d.get("violations") or [])
    return raw, None


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
        "get_scores",
        "Get all dimension scores and grades. Uses the selected run if one is "
        "selected, otherwise the accumulated view (each dimension's latest "
        "run, aggregated — the default dashboard data).",
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
    registry.register(ToolSpec(
        "list_standards", "List all built-in and custom standards.",
        {"type": "object", "properties": {}},
        lambda **kw: _list_standards(ctx, **kw)))
    registry.register(ToolSpec(
        "get_standard", "Get one standard's full principles and requirements.",
        {"type": "object", "properties": {"standard_id": {"type": "string"}},
         "required": ["standard_id"]},
        lambda **kw: _get_standard(ctx, **kw)))
