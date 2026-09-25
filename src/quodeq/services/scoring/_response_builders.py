"""Response builders for the scoring reader.

Builds the camelCase ``{dimensions, summary}`` payloads from either the
SQL grade tables (modern, event-log-projected runs) or the eval JSON
files (legacy runs). Moved out of the package ``__init__`` in the
ScoringReader decomposition; the facade re-exports every name, so
callers and patch targets are unchanged.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from quodeq.shared.serialization import to_camel_dict
from quodeq.core.types.finding import Finding
from quodeq.core.types.finding_type import FindingType
from quodeq.core.scoring.dimension_summary import build_dimension_summary
from quodeq.core.scoring.internals import score_to_grade_label
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams, dimension_weighted_average
from quodeq.core.types.report import PrincipleGrade
from quodeq.core.types.dimension import DimensionResult
from quodeq.services.dashboard import make_run_dimension_fetcher
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys, recount_totals
from quodeq.services.ports import GradeTablesReader
from quodeq.services.wiring import (
    SQLiteStateStore,
    load_suppression_rules,
    read_active_findings,
    row_to_finding,
)
from quodeq.services.rescore import rescore_dimensions
from quodeq.services.scoring._deps import ScoringDeps, NO_DEPS
from quodeq.services.suppression_keys import SuppressionKeys
from quodeq.shared.validation import validate_path_segment


def build_dimension_dict(
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

    files_read = dim_row.get("files_read")
    totals = recount_totals(violations, compliance_count=len(compliance), files_read=files_read)

    dim = DimensionResult(
        dimension=dim_row["dimension"],
        overall_score=overall_score_str,
        overall_grade=overall_grade,
        principles=principles,
        violations=violations,
        compliance=compliance,
        totals=totals,
        files_read=files_read,
    )
    return to_camel_dict(dim)


def build_summary_from_dim_dicts(
    dim_dicts: list[dict], params: ScoringParams = DEFAULT_PARAMS,
    *, score_pairs: list[tuple[str | None, float]],
) -> dict:
    """Build a camelCase summary dict from a list of dimension camelCase dicts.

    Same shape as ``summarize_dimensions`` but working directly on the
    already-serialised dicts produced by ``build_dimension_dict``. The
    grade fallback is deliberately NOT shared: a tied vote resolves here on
    ``Counter`` insertion order (first grade seen wins) and there on grade
    rank, because only the parser side has the rank table. *score_pairs* are
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

    summary = build_dimension_summary(
        len(dim_dicts), overall_grades, overall_grade, numeric_average,
    )
    return to_camel_dict(summary)


def _default_grade_tables_reader(run_dir: Path) -> GradeTablesReader:
    """Composition fallback: the concrete SQLite state store.

    The public caller (``scoring.get_scores_raw``) passes ``store_factory``
    explicitly; this default keeps direct callers of the facade helper
    working without repeating the concrete store at every call site.
    """
    return SQLiteStateStore(run_dir)


def build_response_from_grade_tables(
    run_dir: Path, params: ScoringParams = DEFAULT_PARAMS,
    store_factory: Callable[[Path], GradeTablesReader] | None = None,
    findings_reader: Callable[[Path], Iterable[dict]] | None = None,
) -> dict:
    """Build the full scores response from SQL grade tables + findings.

    Reads dimension_scores and principle_grades from the grade-tables reader
    built by *store_factory* (the SQLite state store by default), reads
    active (non-dismissed) findings via *findings_reader* (the adapter-side
    ``read_active_findings`` by default), and assembles the same camelCase
    dict shape as the legacy rescore path.
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
    for row in (findings_reader or read_active_findings)(run_dir):
        f = row_to_finding(row)
        dim = f.dimension or ""
        if f.verdict == FindingType.VIOLATION:
            violations_by_dim.setdefault(dim, []).append(f)
        else:
            compliance_by_dim.setdefault(dim, []).append(f)

    dim_dicts = []
    score_pairs: list[tuple[str | None, float]] = []
    for dim_row in dim_rows:
        dim_name = dim_row["dimension"]
        dim_dicts.append(build_dimension_dict(
            dim_row,
            p_rows_by_dim.get(dim_name, []),
            violations_by_dim.get(dim_name, []),
            compliance_by_dim.get(dim_name, []),
        ))
        if dim_row.get("score") is not None:
            score_pairs.append((dim_row["dimension"], float(dim_row["score"])))

    summary = build_summary_from_dim_dicts(dim_dicts, params=params, score_pairs=score_pairs)
    return {"dimensions": dim_dicts, "summary": summary}


def build_response_from_eval_files(
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
    d = deps or NO_DEPS
    base_fetcher = make_run_dimension_fetcher(reports_root, project)
    project_dir = reports_root / project
    dismissed = (d.dismissed_keys or dismissed_keys)(project_dir)
    deleted = (d.deleted_keys or deleted_keys)(project_dir)

    dims = base_fetcher(run_id)
    rescored = rescore_dimensions(
        dims, SuppressionKeys(dismissed, deleted, load_suppression_rules(project_dir)),
        params=params, run_dir=project_dir / run_id)
    return {
        "dimensions": rescored.get("dimensions", []),
        "summary": rescored.get("summary", {}),
    }


