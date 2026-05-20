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
from quodeq.core.types.report import PrincipleGrade
from quodeq.core.types.dimension import DimensionResult, DimensionSummary, GradeBreakdown
from quodeq.services.accumulated import compute_accumulated
from quodeq.services.dashboard import (
    DashboardCacheConfig,
    _make_run_dimension_fetcher,
)
from quodeq.services._dashboard_trend import build_accumulated_trend
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services.ports import RunInfo, list_runs
from quodeq.services.rescore import _rescore_dimension, rescore_dimensions
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


def _build_summary_from_dim_dicts(dim_dicts: list[dict]) -> dict:
    """Build a camelCase summary dict from a list of dimension camelCase dicts.

    Mirrors ``summarize_dimensions`` logic but works directly on the already-
    serialised dicts produced by ``_build_dimension_dict``.
    """
    _SCORE_DECIMAL_PLACES = 1
    overall_grades = [d["overallGrade"] for d in dim_dicts if d.get("overallGrade")]
    numeric_scores: list[float] = []
    for d in dim_dicts:
        s = d.get("overallScore")
        if s and isinstance(s, str) and "/" in s:
            try:
                numeric_scores.append(float(s.split("/")[0]))
            except ValueError:
                pass

    numeric_average = None
    if numeric_scores:
        numeric_average = round(sum(numeric_scores) / len(numeric_scores), _SCORE_DECIMAL_PLACES)

    if numeric_average is not None:
        overall_grade = score_to_grade_label(numeric_average)
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


def _build_response_from_grade_tables(run_dir: Path) -> dict:
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
        "scope, req_refs_json, confidence "
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

    summary = _build_summary_from_dim_dicts(dim_dicts)
    return {"dimensions": dim_dicts, "summary": summary}


def _build_response_from_eval_files(
    reports_root: Path, project: str, run_id: str,
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
    rescored = rescore_dimensions(dims, dismissed, deleted)
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

    from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository  # noqa: PLC0415
    from quodeq.data.sqlite.state_store import SQLiteStateStore  # noqa: PLC0415

    # SQL path is meaningful only when events.jsonl exists. For older runs
    # without one, skip straight to the JSON-file fallback so we don't have
    # to wait on a no-op projection that will leave the grade tables empty.
    if (run_dir / "events.jsonl").is_file():
        repo = SqliteFindingsRepository(run_dir)
        repo._ensure_fresh()  # noqa: SLF001
        store = SQLiteStateStore(run_dir)
        if store.read_dimension_scores():
            return _build_response_from_grade_tables(run_dir)

    return _build_response_from_eval_files(reports_root, project, run_id)


def _make_rescoring_fetcher(
    reports_root: Path, project: str,
) -> Callable[[str], list[DimensionResult]]:
    """Return a dimension fetcher that applies rescore (dismissals) to results.

    Wraps the standard cached fetcher so that build_accumulated_trend
    automatically gets rescored data.
    """
    base_fetcher = _make_run_dimension_fetcher(reports_root, project)
    project_dir = reports_root / project
    dismissed = dismissed_keys(project_dir)
    deleted = deleted_keys(project_dir)
    if not dismissed and not deleted:
        return base_fetcher

    def rescoring_fetcher(run_id: str) -> list[DimensionResult]:
        dims = base_fetcher(run_id)
        return [_rescore_dimension(d, dismissed, deleted) for d in dims]

    return rescoring_fetcher


def _rescore_runs_by_dimension(
    dims: list[dict], reports_root: Path, project: str,
    dismissed: set[tuple], deleted: set[tuple] | None = None,
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
            result = rescore_dimensions(run_dims, dismissed, deleted)
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

    rescored_by_dim = _rescore_runs_by_dimension(dims, reports_root, project, dismissed, deleted)
    new_dims = _merge_rescored_dims(dims, rescored_by_dim)

    new_summary = recompute_summary(new_dims, accumulated.get("summary", {}))
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

    all_runs = list_runs(reports_root, project)
    if not all_runs:
        return {
            "accumulated": {"dimensions": [], "summary": {}},
            "trend": [],
            "availableRuns": [],
        }

    # Build accumulated using the existing service (returns full data with violations)
    accumulated = compute_accumulated(
        str(reports_root), project, as_of,
    )
    if accumulated is None:
        accumulated = {"dimensions": [], "summary": {}}

    # Apply rescore to accumulated dimensions
    accumulated = _rescore_accumulated_response(accumulated, reports_root, project)

    # Build trend using a rescoring fetcher (applies dismissals to each run).
    # Exclude cancelled/failed runs — their partial scores are misleading on
    # the history chart. They remain in availableRuns so the UI can show them
    # when the user asks for them explicitly.
    scoreable_runs = [r for r in all_runs if r.status not in ("cancelled", "failed")]
    history_runs = scoreable_runs[:_max_history_runs()]
    rescoring_fetcher = _make_rescoring_fetcher(reports_root, project)
    trend = build_accumulated_trend(history_runs, rescoring_fetcher)

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
    "get_project_scores",
]
