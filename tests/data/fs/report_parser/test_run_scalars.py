"""Tests for read_run_scalars: the lightweight per-run grade reader."""
from pathlib import Path

import pytest

from quodeq.data.fs.report_parser.runs import read_run_data, read_run_scalars
from quodeq.data.sqlite.state_store import SQLiteStateStore
from quodeq.services.dashboard import clear_shared_dimension_cache
from tests.services._scalar_fixtures import build_legacy_run, build_projected_run


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_shared_dimension_cache()
    yield
    clear_shared_dimension_cache()


def test_reads_scalars_from_db_without_findings(tmp_path: Path) -> None:
    reports = tmp_path / "evaluations"
    build_projected_run(reports, "proj", "r1", [
        {"dimension": "security", "severity": "major"},
        {"dimension": "reliability", "severity": "minor"},
    ])

    by_name = {d.dimension: d for d in read_run_scalars(reports, "proj", "r1")}

    assert set(by_name) == {"security", "reliability"}
    assert by_name["security"].overall_score is not None
    assert by_name["security"].overall_grade is not None
    assert by_name["security"].violations == []


def test_scalars_match_read_run_data_scores(tmp_path: Path) -> None:
    reports = tmp_path / "evaluations"
    build_projected_run(reports, "proj", "r1", [
        {"dimension": "security", "severity": "major"},
        {"dimension": "reliability", "severity": "minor"},
    ])

    scalar = {d.dimension: (d.overall_score, d.overall_grade) for d in read_run_scalars(reports, "proj", "r1")}
    heavy = {d.dimension: (d.overall_score, d.overall_grade) for d in read_run_data(reports, "proj", "r1")}
    assert scalar == heavy
    assert all(v[0] is not None for v in scalar.values())


def test_legacy_run_falls_back_to_read_run_data(tmp_path: Path) -> None:
    reports = tmp_path / "evaluations"
    build_legacy_run(reports, "proj", "legacy", {"security": ("7.0/10", "Fair")})

    scalar = read_run_scalars(reports, "proj", "legacy")
    heavy = read_run_data(reports, "proj", "legacy")
    assert [(d.dimension, d.overall_score, d.overall_grade) for d in scalar] == \
           [(d.dimension, d.overall_score, d.overall_grade) for d in heavy]


def test_null_sql_score_falls_back(tmp_path: Path) -> None:
    reports = tmp_path / "evaluations"
    run_dir = build_projected_run(reports, "proj", "r1",
                                  [{"dimension": "security", "severity": "major"}])
    SQLiteStateStore(run_dir).record_dimension_score(
        dimension="reliability", score=None, grade="Insufficient")
    import json
    (run_dir / "evaluation" / "reliability.json").write_text(json.dumps({
        "dimension": "reliability", "overallScore": "no score", "overallGrade": "Insufficient",
        "principles": [], "violations": [], "compliance": [],
        "totals": {"violationCount": 0, "complianceCount": 0, "severity": {}},
    }))
    dims = {d.dimension for d in read_run_scalars(reports, "proj", "r1")}
    assert "reliability" in dims


def test_path_traversal_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        read_run_scalars(tmp_path, "proj", "../escape")
