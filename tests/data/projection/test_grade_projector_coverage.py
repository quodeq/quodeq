"""``recompute_grades`` persists each dimension's coverage from its report."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.events.models import Judgment
from quodeq.data.projection.grade_projector import recompute_grades
from quodeq.data.sqlite.state_store import SQLiteStateStore

_DIM = "Security"
_FILES_READ = 120
_SOURCE_COUNT = 150
_COVERAGE = 80.0


def _seed(run_dir: Path) -> None:
    SQLiteStateStore(run_dir).record_finding(Judgment(
        practice_id="P1", verdict="violation", dimension=_DIM,
        file="a.py", line=1, reason="r", req="S-CON-1", severity="minor",
    ))


def _write_report(run_dir: Path, **fields) -> None:
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(exist_ok=True)
    (eval_dir / f"{_DIM.lower()}.json").write_text(json.dumps({
        "dimension": _DIM.lower(), "principles": [], "violations": [], "compliance": [], **fields,
    }), encoding="utf-8")


def _row(run_dir: Path) -> dict:
    (row,) = SQLiteStateStore(run_dir).read_dimension_scores()
    return row


def test_coverage_columns_round_trip(tmp_path: Path) -> None:
    _seed(tmp_path)
    _write_report(tmp_path, sourceFileCount=_SOURCE_COUNT, filesRead=_FILES_READ,
                  coveragePct=_COVERAGE)
    recompute_grades(tmp_path)
    row = _row(tmp_path)
    assert (row["files_read"], row["source_count"], row["coverage_pct"]) == (
        _FILES_READ, _SOURCE_COUNT, _COVERAGE)


def test_coverage_defaults_when_report_lacks_fields(tmp_path: Path) -> None:
    _seed(tmp_path)
    _write_report(tmp_path)
    recompute_grades(tmp_path)
    row = _row(tmp_path)
    assert (row["files_read"], row["source_count"]) == (0, 0)
