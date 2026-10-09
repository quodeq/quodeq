"""Recompute and write all grade tables from current findings state.

Reads from SQL (so dismissals via verdict='dismissed' are applied automatically),
calls projector_scoring, writes to dimension_scores + principle_grades.

Strategy: full-recompute on every call. Cheap because most projects have <20
dimensions × <20 principles, and SQL aggregation is fast. Avoids dirty-tracking
bugs at the cost of a few ms per call.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from quodeq.core.scoring.params import ScoringParams
from quodeq.core.types.finding import Finding
from quodeq.core.types.finding_type import FindingType
from quodeq.data.fs.grade_formula_store import load_params
from quodeq.data.fs.report_parser.finding_details import iter_readable_eval_reports
from quodeq.data.fs.severity_classes_store import (
    load_severity_classes_for_run,
    severity_classes_fingerprint,
)
from quodeq.data.sqlite.row_mappers import row_to_finding
from quodeq.data.sqlite.connection import open_evaluation_db
from quodeq.data.sqlite.state_store import SQLiteStateStore
from quodeq.shared.constants import JSON_SUFFIX
from quodeq.core.scoring.projector_scoring import (
    GRADE_ALGO_VERSION,
    PrincipleGradeScale,
    compute_dimension_score,
    compute_principle_grade,
)


def _read_source_file_count(run_dir: Path) -> int:
    """Best-effort: pick up the run's ``sourceFileCount`` from any dim JSON.

    The projector needs this to apply the CLI's confidence-level thresholds
    (which scale with project size). Every ``evaluation/<dim>.json`` in the
    run carries the same value; we read the first one we find. Returns 0
    when no JSON exists yet (early projection of a run-in-progress) — that
    falls back to the unsclaed base thresholds in
    ``classify_confidence_level``, matching the CLI's behaviour for runs
    without a known file count.
    """
    for _dimension, data in iter_readable_eval_reports(run_dir):
        if not isinstance(data, dict):
            continue  # a valid-JSON-but-non-dict file: skip, don't crash the loop
        count = data.get("sourceFileCount")
        if isinstance(count, int) and count > 0:
            return count
    return 0


_SELECT_NON_DISMISSED = (
    "SELECT id, practice_id, dimension, requirement, verdict, severity, "
    "file, line, end_line, title, reason, snippet, violation_type, context, "
    "scope, req_refs_json, confidence "
    "FROM findings WHERE verdict != 'dismissed'"
)

_SELECT_DISMISSED_COUNTS = (
    "SELECT dimension, practice_id, COUNT(*) FROM findings "
    "WHERE verdict = 'dismissed' GROUP BY dimension, practice_id"
)


def _dict_row(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def _grade_all_principles(
    violations_by: dict[tuple[str, str], list[Finding]],
    compliance_by: dict[tuple[str, str], list[Finding]],
    dismissed_counts: dict[tuple[str, str], int],
    source_file_count: int,
    params: ScoringParams,
    classes: Mapping[str, str],
) -> tuple[list[tuple[str, dict]], dict[str, list[dict]]]:
    """Compute per-principle grades: flat rows (for persistence) plus the
    same grades grouped by dimension (for the dimension-score rollup)."""
    scale = PrincipleGradeScale(
        source_file_count=source_file_count, params=params, classes=classes)
    principle_grades_by_dim: dict[str, list[dict]] = {}
    principle_rows: list[tuple[str, dict]] = []
    for dim, principle_id in sorted(set(violations_by) | set(compliance_by)):
        grade = compute_principle_grade(
            principle_id=principle_id,
            findings=violations_by.get((dim, principle_id), []),
            compliance=compliance_by.get((dim, principle_id), []),
            dismissed_count=dismissed_counts.get((dim, principle_id), 0),
            scale=scale,
        )
        principle_grades_by_dim.setdefault(dim, []).append(grade)
        principle_rows.append((dim, grade))
    return principle_rows, principle_grades_by_dim


@dataclass(frozen=True, slots=True)
class GradeInputs:
    """What the scorer reads from a run: active findings grouped by
    (dimension, principle), dismissed counts, and the project size."""

    violations_by: dict[tuple[str, str], list[Finding]]
    compliance_by: dict[tuple[str, str], list[Finding]]
    dismissed_counts: dict[tuple[str, str], int]
    source_file_count: int


def load_grade_inputs(run_dir: Path) -> GradeInputs:
    """Read the run's findings from SQL, so dismissals (verdict='dismissed')
    are already applied, and group them for scoring.

    Every stored finding names its principle: projection places findings
    through admission, and one the standard cannot place is kept in
    ``unmapped_findings``, which is never graded.
    """
    with open_evaluation_db(run_dir) as conn:
        dismissed_raw = conn.execute(_SELECT_DISMISSED_COUNTS).fetchall()
        conn.row_factory = _dict_row
        rows = conn.execute(_SELECT_NON_DISMISSED).fetchall()
    violations_by: dict[tuple[str, str], list[Finding]] = {}
    compliance_by: dict[tuple[str, str], list[Finding]] = {}
    for f in (row_to_finding(r) for r in rows):
        bucket = violations_by if f.verdict == FindingType.VIOLATION else compliance_by
        bucket.setdefault((f.dimension or "", f.practice_id), []).append(f)
    dismissed = {(dimension, practice_id): count for dimension, practice_id, count in dismissed_raw}
    return GradeInputs(
        violations_by=violations_by, compliance_by=compliance_by,
        dismissed_counts=dismissed,
        source_file_count=_read_source_file_count(run_dir),
    )


def compute_run_grades(
    run_dir: Path, params: ScoringParams, classes: Mapping[str, str] | None = None,
) -> tuple[list[tuple[str, dict]], list[dict]]:
    """Compute (principle_rows, dimension_rows) from findings. Pure: no writes.

    principle_rows: ``[(dimension, principle_grade_dict), ...]``
    dimension_rows: ``[{"dimension":..., "score":..., "grade":...}, ...]``

    ``recompute_grades`` layers persistence on top; ``preview_scores`` uses
    the result directly. *classes* is the severity class per requirement; None
    loads it for the run's project (standards plus the project's overrides).
    """
    if classes is None:
        classes = load_severity_classes_for_run(run_dir)
    inputs = load_grade_inputs(run_dir)
    principle_rows, principle_grades_by_dim = _grade_all_principles(
        inputs.violations_by, inputs.compliance_by, inputs.dismissed_counts,
        inputs.source_file_count, params, classes,
    )
    dimension_rows = [
        compute_dimension_score(dimension=dim, principle_grades=p_grades, params=params)
        for dim, p_grades in principle_grades_by_dim.items()
    ]
    return principle_rows, dimension_rows


def recompute_grades(
    run_dir: Path, params: ScoringParams | None = None,
    classes: Mapping[str, str] | None = None,
) -> None:
    """Full recompute of dimension_scores + principle_grades from findings.

    When *params* is None, the saved grade-formula params are loaded.
    """
    if params is None:
        params = load_params()
    if classes is None:
        classes = load_severity_classes_for_run(run_dir)
    principle_rows, dimension_rows = compute_run_grades(run_dir, params, classes)

    # Carry the per-dim exit_reason (failure_streak, time_limit, ...) from the
    # authoritative dim-state file so the grade layer can flag/exclude
    # interrupted dimensions. Match case-insensitively: findings carry the
    # dimension label, dimensions.json carries the dimension id.
    from quodeq.data.fs.dimensions_state_store import read_dimensions  # noqa: PLC0415
    dim_states = read_dimensions(run_dir).get("dimensions", {})
    if not isinstance(dim_states, dict):
        dim_states = {}
    exit_by_dim = {
        str(name).lower(): entry.get("exit_reason")
        for name, entry in dim_states.items()
        if isinstance(entry, dict)
    }
    for row in dimension_rows:
        row["exit_reason"] = exit_by_dim.get(str(row["dimension"]).lower())

    # Coverage comes from the dimension report the CLI wrote; the grade
    # tables carry it so the SQL read path can state density per 100 files.
    coverage_by_dim = {
        str(dim_id).lower(): report
        for dim_id, report in iter_readable_eval_reports(run_dir)
        if isinstance(report, dict)
    }
    for row in dimension_rows:
        report = coverage_by_dim.get(str(row["dimension"]).lower(), {})
        row["files_read"] = int(report.get("filesRead") or 0)
        row["source_count"] = int(report.get("sourceFileCount") or 0)
        row["coverage_pct"] = float(report.get("coveragePct") or 0.0)

    store = SQLiteStateStore(run_dir)
    store.batch_rewrite_grades(principle_rows, dimension_rows)
    # Stamp the math these tables now embody, so ensure_projected can tell a
    # run graded with older scoring apart from one that is merely unchanged,
    # and the reports the coverage came from, so a report written after the
    # last event re-derives the tables instead of leaving coverage at zero.
    # The class fingerprint does the same for a standard or override edit.
    # One held connection for the three stamps.
    with store.connection():
        store.save_grades_algo_version(GRADE_ALGO_VERSION)
        store.save_grades_classes_fingerprint(severity_classes_fingerprint(classes))
        store.save_coverage_stamp(report_stamp(run_dir))


def report_stamp(run_dir: Path) -> str:
    """Newest modification time (ns) among ``evaluation/*.json``, ``"0"`` when
    there is none. Cheap to compute (stats only), so staleness checks can use it."""
    eval_dir = run_dir / "evaluation"
    if not eval_dir.is_dir():
        return "0"
    newest = 0
    for path in eval_dir.iterdir():
        if path.suffix == JSON_SUFFIX:
            try:
                newest = max(newest, path.stat().st_mtime_ns)
            except OSError:
                continue
    return str(newest)
