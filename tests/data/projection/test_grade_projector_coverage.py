"""``recompute_grades`` persists each dimension's coverage from its report."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.events.models import Judgment
from quodeq.data.projection.grade_projector import recompute_grades
from quodeq.data.projection.projector import Projector
from quodeq.data.sqlite.state_store import SQLiteStateStore
from tests.api._scores_routes_helpers import _scorable_violations, _seed_run

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


def test_report_written_after_projection_re_derives_coverage(tmp_path: Path) -> None:
    """The CLI writes the report seconds after the last event. A read that
    projects in that window must not freeze the coverage at zero."""
    run_dir = _seed_run(tmp_path, "proj", "r1", _scorable_violations(5, dimension=_DIM.lower()))
    log = run_dir / "events.jsonl"
    assert _row(run_dir)["files_read"] == 0
    _write_report(run_dir, sourceFileCount=_SOURCE_COUNT, filesRead=_FILES_READ,
                  coveragePct=_COVERAGE)
    Projector().ensure_projected(log, run_dir, project_dir=run_dir.parent)
    assert _row(run_dir)["files_read"] == _FILES_READ
