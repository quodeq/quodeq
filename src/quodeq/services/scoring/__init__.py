"""Scoring reader — single read-side entry point for all score data.

Hides the chain of underlying steps (run-dimension fetch, dismissal/deletion
filter, rescore, accumulated aggregation, trend build, summary recompute)
behind a 2-method interface. External callers should never reach into the
private helpers in this package.

Public API
----------
- ``get_scores_raw(reports_root, project, run_id)`` -- rescored dimensions
  and summary for a single run (Explorer detail).
- ``get_project_scores(reports_root, project, as_of)`` -- full dashboard
  payload: accumulated dimensions, summary, trend, available runs.

All functions apply dismissals/deletions server-side and return the same
data shapes as the existing endpoints, so the frontend sees no schema
change.
"""
from __future__ import annotations

import logging
import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

_logger = logging.getLogger(__name__)

from quodeq.core.types import to_camel_dict
from quodeq.core.types.finding import Finding, SeverityTally, Totals
from quodeq.core.scoring.internals import score_to_grade_label
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams, dimension_weighted_average
from quodeq.core.types.report import PrincipleGrade
from quodeq.core.types.dimension import DimensionResult, DimensionSummary, GradeBreakdown
from quodeq.services._dashboard_trend import build_accumulated_trend
from quodeq.services._trend_fetcher import make_rescoring_fetcher, make_trend_fetcher
from quodeq.services.accumulated import compute_accumulated
from quodeq.services.dashboard import _make_run_dimension_fetcher
from quodeq.services.grade_formula import load_params
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services._fs_projects import find_children
from quodeq.services.score_cache import (
    accumulated_cache_version,
    cached_accumulated,
    per_run_versions,
)
from quodeq.services.ports import RunInfo, list_runs, read_run_data, read_run_scalars
from quodeq.services.rescore import _rescore_dimension, rescore_dimensions
from quodeq.shared.validation import validate_path_segment
from quodeq.services.scoring._summary import recompute_summary


def _max_history_runs() -> int:
    """Read max history runs from env at call time for lazy configuration."""
    return int(os.environ.get("QUODEQ_MAX_HISTORY_RUNS", "100"))


# ---------------------------------------------------------------------------
# SQL-backed response builder
# ---------------------------------------------------------------------------

def _severity_bucket(severity: str) -> str:
    """Map DB severity strings to the legacy tally buckets.

    The DB stores ``critical``, ``high``, ``medium``, ``low``, ``minor``. Only
    ``critical``, ``major``, and ``minor`` have dedicated buckets; everything
    else (including ``high``, ``medium``, ``low``) falls into ``unknown``.
    This mirrors the legacy ``recount_totals`` in ``services/dismissed.py`` —
    a pre-existing bucketing semantics worth a follow-up but out of PR 2 scope.
    """
    s = (severity or "").lower()
    if s == "critical":
        return "critical"
    if s == "major":
        return "major"
    if s == "minor":
        return "minor"
    return "unknown"


def _build_totals_from_findings(
    violations: list[Finding], compliance_count: int,
) -> Totals:
    """Build a Totals dataclass from a list of active (non-dismissed) violations."""
    critical = major = minor = unknown = 0
    for v in violations:
        bucket = _severity_bucket(v.severity or "")
        if bucket == "critical":
            critical += 1
        elif bucket == "major":
            major += 1
        elif bucket == "minor":
            minor += 1
        else:
            unknown += 1
    return Totals(
        violation_count=len(violations),
        compliance_count=compliance_count,
        severity=SeverityTally(critical=critical, major=major, minor=minor, unknown=unknown),
    )


def _build_dimension_dict(
    dim_row: dict,
    p_rows: list[dict],
    violations: list[Finding],
    compliance: list[Finding],
) -> dict:
    """Build a single camelCase dimension dict from SQL grade-table rows + findings.

    Produces the same shape as ``to_camel_dict(DimensionResult(...))`` so the
    frontend sees no schema change.
    """
    score_val: float | None = dim_row.get("score")
    overall_score_str = f"{score_val}/10" if score_val is not None else None
    overall_grade = dim_row.get("grade")

    principles = [
        PrincipleGrade(
            principle=p["principle_id"],
            score=f"{p['score']}/10" if p.get("score") is not None else None,
            grade=p.get("grade"),
        )
        for p in p_rows
    ]

    totals = _build_totals_from_findings(violations, compliance_count=len(compliance))

    dim = DimensionResult(
        dimension=dim_row["dimension"],
        overall_score=overall_score_str,
        overall_grade=overall_grade,
        principles=principles,
        violations=violations,
        compliance=compliance,
        totals=totals,
    )
    return to_camel_dict(dim)


def _build_summary_from_dim_dicts(
    dim_dicts: list[dict], params: ScoringParams = DEFAULT_PARAMS,
) -> dict:
    """Build a camelCase summary dict from a list of dimension camelCase dicts.

    Mirrors ``summarize_dimensions`` logic but works directly on the already-
    serialised dicts produced by ``_build_dimension_dict``.
    """
    overall_grades = [d["overallGrade"] for d in dim_dicts if d.get("overallGrade")]
    score_pairs: list[tuple[str | None, float]] = []
    for d in dim_dicts:
        s = d.get("overallScore")
        if s and isinstance(s, str) and "/" in s:
            try:
                score_pairs.append((d.get("dimension"), float(s.split("/")[0])))
            except ValueError:
                pass

    numeric_average = dimension_weighted_average(score_pairs, params)

    if numeric_average is not None:
        overall_grade = score_to_grade_label(numeric_average, params=params)
    elif overall_grades:
        from collections import Counter  # noqa: PLC0415
        overall_grade = Counter(overall_grades).most_common(1)[0][0]
    else:
        overall_grade = None

    grade_counts: dict[str, int] = {}
    for g in overall_grades:
        grade_counts[g] = grade_counts.get(g, 0) + 1

    summary = DimensionSummary(
        dimensions_count=len(dim_dicts),
        overall_grade=overall_grade,
        numeric_average=numeric_average,
        grade_breakdown=[
            GradeBreakdown(grade=grade, count=count)
            for grade, count in sorted(grade_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
    )
    return to_camel_dict(summary)


def _build_response_from_grade_tables(
    run_dir: Path, params: ScoringParams = DEFAULT_PARAMS,
) -> dict:
    """Build the full scores response from SQL grade tables + findings.

    Reads dimension_scores and principle_grades from the state store, reads
    active (non-dismissed) findings from the findings table, and assembles
    the same camelCase dict shape as the legacy rescore path.
    """
    from quodeq.data.sqlite.state_store import SQLiteStateStore  # noqa: PLC0415
    from quodeq.data.sqlite.connection import open_evaluation_db  # noqa: PLC0415
    from quodeq.data.sqlite._row_mappers import row_to_finding  # noqa: PLC0415

    store = SQLiteStateStore(run_dir)
    dim_rows = store.read_dimension_scores()
    p_rows = store.read_principle_grades()

    # Group principle rows by dimension for fast lookup.
    p_rows_by_dim: dict[str, list[dict]] = {}
    for p in p_rows:
        p_rows_by_dim.setdefault(p["dimension"], []).append(p)

    # Read active findings grouped by dimension and verdict.
    _SELECT_ACTIVE = (
        "SELECT id, practice_id, dimension, requirement, verdict, severity, "
        "file, line, end_line, title, reason, snippet, violation_type, context, "
        "scope, req_refs_json, confidence, provenance_downgrade "
        "FROM findings WHERE verdict != 'dismissed' ORDER BY id"
    )

    def _dict_row(cursor, row):  # noqa: ANN001
        return {col[0]: row[i] for i, col in enumerate(cursor.description)}

    violations_by_dim: dict[str, list[Finding]] = {}
    compliance_by_dim: dict[str, list[Finding]] = {}
    with open_evaluation_db(run_dir) as conn:
        conn.row_factory = _dict_row
        rows = conn.execute(_SELECT_ACTIVE).fetchall()

    for row in rows:
        f = row_to_finding(row)
        dim = f.dimension or ""
        if f.verdict == "violation":
            violations_by_dim.setdefault(dim, []).append(f)
        else:
            compliance_by_dim.setdefault(dim, []).append(f)

    dim_dicts = []
    for dim_row in dim_rows:
        dim_name = dim_row["dimension"]
        dim_dicts.append(_build_dimension_dict(
            dim_row,
            p_rows_by_dim.get(dim_name, []),
            violations_by_dim.get(dim_name, []),
            compliance_by_dim.get(dim_name, []),
        ))

    summary = _build_summary_from_dim_dicts(dim_dicts, params=params)
    return {"dimensions": dim_dicts, "summary": summary}


def _build_response_from_eval_files(
    reports_root: Path, project: str, run_id: str,
    params: ScoringParams = DEFAULT_PARAMS,
) -> dict:
    """Read eval JSON files for a run and apply rescore (legacy path).

    Used for older runs that pre-date the event-log scoring engine. Those runs
    never get an ``events.jsonl`` so SQL projection has nothing to chew on —
    the dim_scores / principle_grades tables stay empty forever. But the JSON
    files (``evaluation/<dim>.json``) hold the original scores, and dismisses
    on actions.jsonl can be applied via the same ``rescore_dimensions`` helper
    the dashboard already uses for accumulated data.

    Returns the same camelCase ``{dimensions, summary}`` shape as the SQL
    path, so callers (UI dismiss handlers) don't need to branch.
    """
    base_fetcher = _make_run_dimension_fetcher(reports_root, project)
    project_dir = reports_root / project
    dismissed = dismissed_keys(project_dir)
    deleted = deleted_keys(project_dir)

    dims = base_fetcher(run_id)
    rescored = rescore_dimensions(dims, dismissed, deleted, params=params)
    return {
        "dimensions": rescored.get("dimensions", []),
        "summary": rescored.get("summary", {}),
    }


def get_scores_raw(
    reports_root: Path, project: str, run_id: str,
) -> dict:
    """Return raw rescore dict for a single run (explorer detail compat).

    Tries SQL grade tables first (fast path for runs projected from
    events.jsonl). Falls back to reading the eval JSON files + applying
    rescore when SQL is empty — this is the case for older runs that
    pre-date the event-log scoring engine. Without this fallback, ~all
    pre-event-log runs returned an empty ``{dimensions: [], summary: {}}``
    payload, which made live-grade updates impossible for them: the dismiss
    POST returned no scores, the UI had nothing to apply.
    """
    run_dir = reports_root / project / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    params = load_params()

    from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository  # noqa: PLC0415
    from quodeq.data.sqlite.state_store import SQLiteStateStore  # noqa: PLC0415

    # The SQL grade tables are frozen per run and, on a stale projection,
    # reflect only the dismissals already projected into THIS run's own findings
    # table -- NOT project-wide dismissals/deletions that accrued later. So when
    # the project has active dismissals/deletions AND this run has eval JSON to
    # rescore from, defer to the eval-file path, which applies the project-wide
    # dismiss set authoritatively via ``rescore_dimensions`` -- the SAME
    # transform the accumulated view uses, so every per-run read agrees on the
    # dismiss-adjusted score. Event-log-only runs (no eval JSON) can't be
    # rescored that way; they keep the SQL path, whose ``_ensure_fresh``
    # re-projection applies the dismissals directly to the findings table.
    project_dir = reports_root / project
    has_project_wide_filters = bool(dismissed_keys(project_dir) or deleted_keys(project_dir))
    eval_dir = run_dir / "evaluation"
    prefer_eval_rescore = (
        has_project_wide_filters
        and eval_dir.is_dir()
        and any(p.suffix == ".json" for p in eval_dir.iterdir())
    )

    # SQL path is meaningful only when events.jsonl exists. For older runs
    # without one, skip straight to the JSON-file fallback so we don't have
    # to wait on a no-op projection that will leave the grade tables empty.
    if not prefer_eval_rescore and (run_dir / "events.jsonl").is_file():
        import sqlite3  # noqa: PLC0415
        try:
            repo = SqliteFindingsRepository(run_dir)
            repo._ensure_fresh()  # noqa: SLF001
            store = SQLiteStateStore(run_dir)
            if store.read_dimension_scores():
                return _build_response_from_grade_tables(run_dir, params=params)
        except sqlite3.DatabaseError:
            # evaluation.db is unreadable by this binary: it was written by a
            # newer Quodeq (SchemaVersionError, a DatabaseError subclass) or is
            # otherwise corrupt/half-written. Don't crash the score read; fall
            # back to the JSON eval files (schema-independent) so a downgraded
            # or upgrading install still works.
            _logger.warning(
                "Run %s/%s has an unreadable evaluation.db; serving scores "
                "from the JSON eval files instead of the SQL grade tables.",
                project, run_id,
            )

    return _build_response_from_eval_files(reports_root, project, run_id, params=params)


def get_scores_slim(
    reports_root: Path, project: str, run_id: str,
) -> dict:
    """``get_scores_raw`` with finding bodies stripped for the run-scores route.

    The Explorer (the endpoint's only consumer) uses the response to overlay
    dismissal-aware scores onto the eval payload it fetched separately: it
    reads per-dimension/per-principle score + grade + totals, and uses each
    violation solely as a ``req|file|line`` identity key to filter dismissed
    findings out of the eval data. Returning full bodies made the response
    7+ MB on finding-heavy runs; the slim form carries the same information
    the merge needs at a fraction of the size. Compliance bodies are never
    read from this payload, so the list is emptied (counts live in totals).
    """
    raw = get_scores_raw(reports_root, project, run_id)
    slim_dims = []
    for dim in raw.get("dimensions", []) or []:
        slim_violations = [
            {"req": v.get("req"), "file": v.get("file"), "line": v.get("line")}
            for v in (dim.get("violations") or [])
        ]
        slim_dims.append({**dim, "violations": slim_violations, "compliance": []})
    return {**raw, "dimensions": slim_dims}


def scored_run_dimensions(
    reports_root: Path, project: str, run_id: str,
    params: ScoringParams | None = None,
) -> list[DimensionResult]:
    """Return a run's dimensions with the project-wide dismiss/delete rescore applied.

    This is the single seam every per-run read path routes through so the SAME
    run+dimension reports the SAME score everywhere. It is
    ``read_run_data`` (raw, dismissals NOT applied) composed with the same
    project-wide ``_rescore_dimension`` the accumulated view already runs, and
    returns ``DimensionResult`` objects (not camelCase dicts).

    Rescore is deliberately kept *out* of ``read_run_data`` itself: that
    function is foundational and feeds exports and other callers that must see
    the raw scan. Callers that want the dismiss-adjusted view ask for it here.

    When *params* is None the saved grade-formula params are loaded, matching
    ``get_scores_raw`` / ``build_dashboard``.
    """
    validate_path_segment(project, run_id)
    if params is None:
        params = load_params()
    project_dir = reports_root / project
    dismissed = dismissed_keys(project_dir)
    deleted = deleted_keys(project_dir)
    dims = read_run_data(reports_root, project, run_id)
    if not dismissed and not deleted:
        return dims
    return [_rescore_dimension(d, dismissed, deleted, params=params) for d in dims]


def _make_rescoring_fetcher(
    reports_root: Path, project: str,
    params: ScoringParams = DEFAULT_PARAMS,
) -> Callable[[str], list[DimensionResult]]:
    """Return a dimension fetcher that applies rescore (dismissals) to results.

    Thin seam over the shared :func:`make_rescoring_fetcher` factory. Passes the
    scoring module's own ``dismissed_keys`` / ``deleted_keys`` references so
    monkeypatch-based tests keep working, and the full-data base fetcher.
    """
    return make_rescoring_fetcher(
        reports_root, project, params=params,
        base_fetcher=_make_run_dimension_fetcher(reports_root, project),
        dismissed_keys=dismissed_keys, deleted_keys=deleted_keys,
    )


def _make_trend_fetcher(
    reports_root: Path, project: str,
    params: ScoringParams = DEFAULT_PARAMS,
    cacheable_run_ids: set[str] | None = None,
) -> Callable[[str], list[DimensionResult]]:
    """Return the dimension fetcher for the trend chart.

    Thin seam over the shared :func:`make_trend_fetcher` factory, passing the
    scoring module's own ``read_run_scalars`` / ``dismissed_keys`` /
    ``deleted_keys`` references (so this module's monkeypatch-based tests keep
    working) and the shared full-data base-fetcher factory. See
    :func:`make_trend_fetcher` for the fast/heavy path and caching semantics.
    """
    return make_trend_fetcher(
        reports_root, project, params=params, cacheable_run_ids=cacheable_run_ids,
        max_history=_max_history_runs(),
        base_fetcher_factory=_make_run_dimension_fetcher,
        read_run_scalars=read_run_scalars,
        dismissed_keys=dismissed_keys, deleted_keys=deleted_keys,
    )


def _rescore_runs_by_dimension(
    dims: list[dict], reports_root: Path, project: str,
    dismissed: set[tuple], deleted: set[tuple] | None = None,
    params: ScoringParams = DEFAULT_PARAMS,
) -> dict[str, dict]:
    """Rescore each unique run and return a map of dim_key -> rescored dict."""
    dim_to_run: dict[str, str] = {}
    for d in dims:
        key = (d.get("dimension") or "").lower()
        rid = d.get("fromRunId") or d.get("runId")
        if key and rid:
            dim_to_run[key] = rid

    fetcher = _make_run_dimension_fetcher(reports_root, project)
    rescored_by_dim: dict[str, dict] = {}
    seen_runs: dict[str, dict[str, dict]] = {}
    for dim_key, run_id in dim_to_run.items():
        if run_id not in seen_runs:
            run_dims = fetcher(run_id)
            result = rescore_dimensions(run_dims, dismissed, deleted, params=params)
            seen_runs[run_id] = {
                (rd.get("dimension") or "").lower(): rd
                for rd in result.get("dimensions", [])
            }
        rd = seen_runs[run_id].get(dim_key)
        if rd:
            rescored_by_dim[dim_key] = rd
    return rescored_by_dim


def _merge_rescored_dims(dims: list[dict], rescored_by_dim: dict[str, dict]) -> list[dict]:
    """Merge rescored data into accumulated dimensions."""
    new_dims = []
    for d in dims:
        key = (d.get("dimension") or "").lower()
        rd = rescored_by_dim.get(key)
        if rd:
            new_dims.append({
                **d,
                "overallScore": rd.get("overallScore"),
                "overallGrade": rd.get("overallGrade"),
                "violations": rd.get("violations", d.get("violations", [])),
                "compliance": rd.get("compliance", d.get("compliance", [])),
                "principles": rd.get("principles", d.get("principles", [])),
                "totals": rd.get("totals", d.get("totals")),
            })
        else:
            new_dims.append(d)
    return new_dims


def _rescore_accumulated_response(
    accumulated: dict[str, Any],
    reports_root: Path,
    project: str,
    params: ScoringParams = DEFAULT_PARAMS,
) -> dict[str, Any]:
    """Apply rescore to an accumulated response dict (in-place compatible shape).

    Filters dismissed violations from each dimension, recalculates scores,
    and recomputes the summary.
    """
    project_dir = reports_root / project
    dismissed = dismissed_keys(project_dir)
    deleted = deleted_keys(project_dir)
    if (not dismissed and not deleted) or not accumulated:
        return accumulated

    dims = accumulated.get("dimensions", [])
    if not dims:
        return accumulated

    rescored_by_dim = _rescore_runs_by_dimension(
        dims, reports_root, project, dismissed, deleted, params=params,
    )
    new_dims = _merge_rescored_dims(dims, rescored_by_dim)

    new_summary = recompute_summary(new_dims, accumulated.get("summary", {}), params=params)
    return {**accumulated, "dimensions": new_dims, "summary": new_summary}


def get_project_scores(
    reports_root: Path, project: str, as_of: str | None = None,
) -> dict[str, Any] | None:
    """Return the full scores payload for the dashboard.

    Returns a dict with:
      - accumulated: { dimensions, summary } (same shape as /accumulated endpoint)
      - trend: [{ runId, dateISO, ... }] (same shape as dashboard.trend)
      - availableRuns: [{ runId, dateLabel }]

    All scores have dismissals applied server-side.
    """
    if not (reports_root / project).exists():
        return None

    params = load_params()

    all_runs = list_runs(reports_root, project)
    if not all_runs:
        return {
            "accumulated": {"dimensions": [], "summary": {}},
            "trend": [],
            "availableRuns": [],
        }

    # Build accumulated using the existing service (returns full data with violations)
    def _compute_accumulated_payload() -> dict:
        acc = compute_accumulated(str(reports_root), project, as_of, params=params)
        if acc is None:
            acc = {"dimensions": [], "summary": {}}
        return _rescore_accumulated_response(acc, reports_root, project, params=params)

    if find_children(reports_root, project):
        # Parent aggregation pulls child projects' dismissals/runs into the
        # payload, which the project-scoped cache version can't see -- bypass
        # the cache for parents to avoid serving stale data.
        accumulated = _compute_accumulated_payload()
    else:
        acc_version = accumulated_cache_version(
            reports_root / project, params,
            per_run_versions(reports_root / project, project, params,
                             [(r.run_id, r.status) for r in all_runs]),
            as_of,
        )
        accumulated = cached_accumulated(project, acc_version, _compute_accumulated_payload)

    # Build trend using the appropriate fetcher: scalar fast path when there
    # are no active dismissals/deletions, rescoring (findings) path otherwise.
    # Exclude cancelled/failed runs — their partial scores are misleading on
    # the history chart. They remain in availableRuns so the UI can show them
    # when the user asks for them explicitly.
    scoreable_runs = [r for r in all_runs if r.status not in ("cancelled", "failed")]
    history_runs = scoreable_runs[:_max_history_runs()]
    # Only completed runs may be persisted to the score cache: an in-progress
    # run's scalar set is still growing, and the cache version can't see that,
    # so caching its partial set would strand a stale row (e.g. 1 of 6 dims)
    # served forever after the run finishes.
    cacheable_run_ids = {r.run_id for r in history_runs if r.status == "complete"}
    trend_fetcher = _make_trend_fetcher(
        reports_root, project, params=params, cacheable_run_ids=cacheable_run_ids,
    )
    trend = build_accumulated_trend(history_runs, trend_fetcher, params=params)

    # Build available runs list
    available_runs = [
        {"runId": r.run_id, "dateLabel": r.date_label, "status": r.status}
        for r in all_runs
    ]

    return {
        "accumulated": accumulated,
        "trend": trend,
        "availableRuns": available_runs,
    }


__all__ = [
    "get_scores_raw",
    "get_scores_slim",
    "get_project_scores",
    "scored_run_dimensions",
]
