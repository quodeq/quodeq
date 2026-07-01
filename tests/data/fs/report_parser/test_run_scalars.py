"""Tests for read_run_scalars: the lightweight per-run grade reader."""
import json
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
    build_projected_run(reports, "proj", "r1",
                        {"security": (8.5, "Good"), "reliability": (6.0, "Fair")})

    by_name = {d.dimension: d for d in read_run_scalars(reports, "proj", "r1")}

    assert set(by_name) == {"security", "reliability"}
    assert by_name["security"].overall_score is not None
    assert by_name["security"].overall_grade is not None
    assert by_name["security"].violations == []


def test_scalars_match_read_run_data_scores(tmp_path: Path) -> None:
    reports = tmp_path / "evaluations"
    build_projected_run(reports, "proj", "r1",
                        {"security": (8.5, "Good"), "reliability": (6.0, "Fair")})

    scalar = {d.dimension: (d.overall_score, d.overall_grade) for d in read_run_scalars(reports, "proj", "r1")}
    heavy = {d.dimension: (d.overall_score, d.overall_grade) for d in read_run_data(reports, "proj", "r1")}
    # Equal to each other AND to the concrete non-NULL values: proves the fast
    # path returns real scores, not "None/10" from a silent fallback.
    assert scalar == heavy
    assert scalar == {
        "security": ("8.5/10", "Good"),
        "reliability": ("6.0/10", "Fair"),
    }


def test_legacy_run_falls_back_to_read_run_data(tmp_path: Path) -> None:
    reports = tmp_path / "evaluations"
    build_legacy_run(reports, "proj", "legacy", {"security": ("7.0/10", "Fair")})

    scalar = read_run_scalars(reports, "proj", "legacy")
    heavy = read_run_data(reports, "proj", "legacy")
    assert [(d.dimension, d.overall_score, d.overall_grade) for d in scalar] == \
           [(d.dimension, d.overall_score, d.overall_grade) for d in heavy]


def test_null_sql_score_falls_back(tmp_path: Path, monkeypatch) -> None:
    reports = tmp_path / "evaluations"
    run_dir = build_projected_run(reports, "proj", "r1", {"security": (8.5, "Good")})
    SQLiteStateStore(run_dir).record_dimension_score(
        dimension="reliability", score=None, grade="Insufficient")
    (run_dir / "evaluation" / "reliability.json").write_text(json.dumps({
        "dimension": "reliability", "overallScore": "no score", "overallGrade": "Insufficient",
        "principles": [], "violations": [], "compliance": [],
        "totals": {"violationCount": 0, "complianceCount": 0, "severity": {}},
    }))

    import quodeq.data.fs.report_parser.runs as runs_mod
    fell_back = []
    orig = runs_mod.read_run_data
    monkeypatch.setattr(runs_mod, "read_run_data",
                        lambda *a, **k: (fell_back.append(True), orig(*a, **k))[1])

    dims = {d.dimension for d in read_run_scalars(reports, "proj", "r1")}
    assert fell_back, "expected fallback to read_run_data on NULL SQL score"
    assert "reliability" in dims


def test_partial_projection_falls_back(tmp_path: Path, monkeypatch) -> None:
    reports = tmp_path / "evaluations"
    run_dir = build_projected_run(reports, "proj", "r1", {"security": (8.5, "Good")})
    # A second eval JSON with no matching SQL dimension row → count mismatch.
    (run_dir / "evaluation" / "reliability.json").write_text(json.dumps({
        "dimension": "reliability", "overallScore": "7.0/10", "overallGrade": "Fair",
        "principles": [], "violations": [], "compliance": [],
        "totals": {"violationCount": 0, "complianceCount": 0, "severity": {}},
    }))
    import quodeq.data.fs.report_parser.runs as runs_mod
    fell_back = []
    orig = runs_mod.read_run_data
    monkeypatch.setattr(runs_mod, "read_run_data",
                        lambda *a, **k: (fell_back.append(True), orig(*a, **k))[1])
    read_run_scalars(reports, "proj", "r1")
    assert fell_back, "expected fallback when SQL dim count != on-disk JSON count"


def test_path_traversal_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        read_run_scalars(tmp_path, "proj", "../escape")


def test_fast_path_does_not_fall_back(tmp_path: Path, monkeypatch) -> None:
    """With non-NULL SQL scores, read_run_scalars must NOT call read_run_data."""
    reports = tmp_path / "evaluations"
    build_projected_run(reports, "proj", "r1", {"security": (8.5, "Good")})

    import quodeq.data.fs.report_parser.runs as runs_mod

    def boom(*_a, **_k):
        raise AssertionError("read_run_scalars fell back to read_run_data")
    monkeypatch.setattr(runs_mod, "read_run_data", boom)

    dims = {d.dimension: d.overall_score for d in read_run_scalars(reports, "proj", "r1")}
    assert dims == {"security": "8.5/10"}
