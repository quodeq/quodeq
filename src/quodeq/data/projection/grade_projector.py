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
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
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


def recompute_grades(run_dir: Path) -> None:
    """Full recompute of dimension_scores + principle_grades from findings."""
    store = SQLiteStateStore(run_dir)
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
    all_principle_keys = set(violations_by) | set(compliance_by)
    principle_rows_to_write = []
    for dim, principle_id in sorted(all_principle_keys):
        p_violations = violations_by.get((dim, principle_id), [])
        p_compliance = compliance_by.get((dim, principle_id), [])
        dismissed = dismissed_counts.get((dim, principle_id), 0)
        grade = compute_principle_grade(
            principle_id=principle_id,
            findings=p_violations,
            compliance=p_compliance,
            dismissed_count=dismissed,
            source_file_count=source_file_count,
        )
        principle_grades_by_dim.setdefault(dim, []).append(grade)
        principle_rows_to_write.append((dim, grade))

    # Clear and rewrite both tables.
    store.clear_grades()
    for dim, p_grade in principle_rows_to_write:
        store.record_principle_grade(
            dimension=dim,
            principle_id=p_grade["principle_id"],
            score=p_grade["score"],
            grade=p_grade["grade"],
            finding_count=p_grade["finding_count"],
            dismissed_count=p_grade["dismissed_count"],
        )

    for dim, p_grades in principle_grades_by_dim.items():
        d_score = compute_dimension_score(dimension=dim, principle_grades=p_grades)
        store.record_dimension_score(
            dimension=dim,
            score=d_score["score"],
            grade=d_score["grade"],
        )
