"""The dimension eval payload carries the grade tables' scores, dismissals or not.

The grade tables are re-derived whenever the scoring formula changes, so
the principle scores frozen in ``evaluation/<dim>.json`` at eval time go
stale without a single dismissal. Every other view reads the tables; the
dimension page must too, or its header and its principle cards disagree.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.data.sqlite.state_store import SQLiteStateStore
from quodeq.services.fs_reports import get_dimension_eval
from tests.api._scores_routes_helpers import _scorable_violations, _seed_run

_PROJECT = "proj"
_RUN = "run1"
_DIM = "security"
_PRINCIPLE = "Confidentiality"  # a canonical security principle, so the parser keeps it
_STALE_SCORE = "1.0/10"


def _write_eval_json(run_dir: Path) -> None:
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(exist_ok=True)
    (eval_dir / f"{_DIM}.json").write_text(json.dumps({
        "dimension": _DIM, "overallScore": _STALE_SCORE, "overallGrade": "Poor",
        "principles": [{"name": _PRINCIPLE, "score": _STALE_SCORE, "grade": "Poor"}],
        "violations": [], "compliance": [],
    }), encoding="utf-8")


def test_principle_scores_come_from_grade_tables_without_dismissals(tmp_path: Path) -> None:
    run_dir = _seed_run(
        tmp_path, _PROJECT, _RUN, _scorable_violations(5, practice=_PRINCIPLE, dimension=_DIM),
    )
    _write_eval_json(run_dir)
    (sql_row,) = SQLiteStateStore(run_dir).read_principle_grades()
    expected = f"{sql_row['score']}/10"
    assert expected != _STALE_SCORE

    payload = get_dimension_eval(str(tmp_path), _PROJECT, _RUN, _DIM)

    assert isinstance(payload, dict)
    assert [p["score"] for p in payload["principles"]] == [expected]
    by_name = {pg["principle"]: pg["score"] for pg in payload["principleGrades"]}
    assert by_name[_PRINCIPLE] == expected
