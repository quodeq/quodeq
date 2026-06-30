"""Recompute and write all grade tables from current findings state.

Reads from SQL (so dismissals via verdict='dismissed' are applied automatically),
calls projector_scoring, writes to dimension_scores + principle_grades.

Strategy: full-recompute on every call. Cheap because most projects have <20
dimensions × <20 principles, and SQL aggregation is fast. Avoids dirty-tracking
bugs at the cost of a few ms per call.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.scoring.params import ScoringParams
from quodeq.core.types.finding import Finding
from quodeq.data.sqlite._row_mappers import row_to_finding
from quodeq.data.sqlite.connection import open_evaluation_db
from quodeq.data.sqlite.state_store import SQLiteStateStore
from quodeq.services.scoring.projector_scoring import (
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
    eval_dir = run_dir / "evaluation"
    if not eval_dir.is_dir():
        return 0
    for path in eval_dir.iterdir():
        if path.suffix != ".json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
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


def compute_run_grades(
    run_dir: Path, params: ScoringParams,
) -> tuple[list[tuple[str, dict]], list[dict]]:
    """Compute (principle_rows, dimension_rows) from findings. Pure: no writes.

    principle_rows: ``[(dimension, principle_grade_dict), ...]``
    dimension_rows: ``[{"dimension":..., "score":..., "grade":...}, ...]``

    Reads from SQL (so dismissals via verdict='dismissed' are applied
    automatically) but never touches the grade tables. ``recompute_grades``
    layers persistence on top; ``preview_scores`` uses the result directly.
    """
    source_file_count = _read_source_file_count(run_dir)

    with open_evaluation_db(run_dir) as conn:
        # Fetch dismissed counts as plain tuples before switching row_factory.
        dismissed_raw = conn.execute(_SELECT_DISMISSED_COUNTS).fetchall()
        dismissed_counts = {(r[0], r[1]): r[2] for r in dismissed_raw}

        conn.row_factory = _dict_row
        rows = conn.execute(_SELECT_NON_DISMISSED).fetchall()

    findings = [row_to_finding(r) for r in rows]

    # Group by (dimension, principle) for violations vs compliance.
    violations_by: dict[tuple[str, str], list[Finding]] = {}
    compliance_by: dict[tuple[str, str], list[Finding]] = {}
    for f in findings:
        key = (f.dimension or "", f.practice_id or "")
        bucket = violations_by if f.verdict == "violation" else compliance_by
        bucket.setdefault(key, []).append(f)

    # Compute per-principle grades, group results by dimension.
    principle_grades_by_dim: dict[str, list[dict]] = {}
    principle_rows: list[tuple[str, dict]] = []
    for dim, principle_id in sorted(set(violations_by) | set(compliance_by)):
        grade = compute_principle_grade(
            principle_id=principle_id,
            findings=violations_by.get((dim, principle_id), []),
            compliance=compliance_by.get((dim, principle_id), []),
            dismissed_count=dismissed_counts.get((dim, principle_id), 0),
            source_file_count=source_file_count,
            params=params,
        )
        principle_grades_by_dim.setdefault(dim, []).append(grade)
        principle_rows.append((dim, grade))

    dimension_rows = [
        compute_dimension_score(dimension=dim, principle_grades=p_grades, params=params)
        for dim, p_grades in principle_grades_by_dim.items()
    ]
    return principle_rows, dimension_rows


def recompute_grades(run_dir: Path, params: ScoringParams | None = None) -> None:
    """Full recompute of dimension_scores + principle_grades from findings.

    When *params* is None, the saved grade-formula params are loaded.
    """
    if params is None:
        from quodeq.services import grade_formula  # noqa: PLC0415
        params = grade_formula.load_params()
    principle_rows, dimension_rows = compute_run_grades(run_dir, params)

    store = SQLiteStateStore(run_dir)
    store.batch_rewrite_grades(principle_rows, dimension_rows)
