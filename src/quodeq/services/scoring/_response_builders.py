"""Response builders for the scoring reader.

Builds the camelCase ``{dimensions, summary}`` payloads from either the
SQL grade tables (modern, event-log-projected runs) or the eval JSON
files (legacy runs). Moved out of the package ``__init__`` in the
ScoringReader decomposition; the facade re-exports every name, so
callers and patch targets are unchanged.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from quodeq.shared.serialization import to_camel_dict
from quodeq.core.types.finding import Finding, SeverityTally, Totals
from quodeq.core.scoring.internals import score_to_grade_label
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams, dimension_weighted_average
from quodeq.core.types.report import PrincipleGrade
from quodeq.core.types.dimension import DimensionResult, DimensionSummary, GradeBreakdown
from quodeq.services.dashboard import _make_run_dimension_fetcher
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services.ports import GradeTablesReader
from quodeq.services._wiring import (
    SQLiteStateStore,
    load_suppression_rules,
    read_active_findings,
    row_to_finding,
)
from quodeq.services.rescore import rescore_dimensions
from quodeq.services.scoring._deps import ScoringDeps, _NO_DEPS
from quodeq.shared.validation import validate_path_segment


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
    *, score_pairs: list[tuple[str | None, float]],
) -> dict:
    """Build a camelCase summary dict from a list of dimension camelCase dicts.

    Mirrors ``summarize_dimensions`` logic but works directly on the already-
    serialised dicts produced by ``_build_dimension_dict``. *score_pairs* are
    the raw (dimension, score) floats -- the caller already has them before
    they get formatted into the ``overallScore`` display strings, so no
    parsing back out of ``"7.5/10"`` is needed here.
    """
    overall_grades = [d["overallGrade"] for d in dim_dicts if d.get("overallGrade")]

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


def _default_grade_tables_reader(run_dir: Path) -> GradeTablesReader:
    """Composition fallback: the concrete SQLite state store.

    The public caller (``scoring.get_scores_raw``) passes ``store_factory``
    explicitly; this default keeps direct callers of the facade helper
    working without repeating the concrete store at every call site.
    """
    return SQLiteStateStore(run_dir)


def _build_response_from_grade_tables(
    run_dir: Path, params: ScoringParams = DEFAULT_PARAMS,
    store_factory: Callable[[Path], GradeTablesReader] | None = None,
) -> dict:
    """Build the full scores response from SQL grade tables + findings.

    Reads dimension_scores and principle_grades from the grade-tables reader
    built by *store_factory* (the SQLite state store by default), reads
    active (non-dismissed) findings via the adapter-side
    ``read_active_findings``, and assembles the same camelCase dict shape as
    the legacy rescore path.
    """
    store = (store_factory or _default_grade_tables_reader)(run_dir)
    dim_rows = store.read_dimension_scores()
    p_rows = store.read_principle_grades()

    # Group principle rows by dimension for fast lookup.
    p_rows_by_dim: dict[str, list[dict]] = {}
    for p in p_rows:
        p_rows_by_dim.setdefault(p["dimension"], []).append(p)

    # Active findings grouped by dimension and verdict.
    violations_by_dim: dict[str, list[Finding]] = {}
    compliance_by_dim: dict[str, list[Finding]] = {}
    for row in read_active_findings(run_dir):
        f = row_to_finding(row)
        dim = f.dimension or ""
        if f.verdict == "violation":
            violations_by_dim.setdefault(dim, []).append(f)
        else:
            compliance_by_dim.setdefault(dim, []).append(f)

    dim_dicts = []
    score_pairs: list[tuple[str | None, float]] = []
    for dim_row in dim_rows:
        dim_name = dim_row["dimension"]
        dim_dicts.append(_build_dimension_dict(
            dim_row,
            p_rows_by_dim.get(dim_name, []),
            violations_by_dim.get(dim_name, []),
            compliance_by_dim.get(dim_name, []),
        ))
        if dim_row.get("score") is not None:
            score_pairs.append((dim_row["dimension"], float(dim_row["score"])))

    summary = _build_summary_from_dim_dicts(dim_dicts, params=params, score_pairs=score_pairs)
    return {"dimensions": dim_dicts, "summary": summary}


def _build_response_from_eval_files(
    reports_root: Path, project: str, run_id: str,
    params: ScoringParams = DEFAULT_PARAMS,
    deps: ScoringDeps | None = None,
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
    validate_path_segment(project, run_id)
    d = deps or _NO_DEPS
    base_fetcher = _make_run_dimension_fetcher(reports_root, project)
    project_dir = reports_root / project
    dismissed = (d.dismissed_keys or dismissed_keys)(project_dir)
    deleted = (d.deleted_keys or deleted_keys)(project_dir)

    dims = base_fetcher(run_id)
    rescored = rescore_dimensions(
        dims, dismissed, deleted, params=params, run_dir=project_dir / run_id,
        rules=load_suppression_rules(project_dir))
    return {
        "dimensions": rescored.get("dimensions", []),
        "summary": rescored.get("summary", {}),
    }


