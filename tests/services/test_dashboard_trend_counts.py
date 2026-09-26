"""Trend rows carry the counts that converge, not only the score."""
from __future__ import annotations

from quodeq.core.types import DimensionResult
from quodeq.core.types.finding import Finding
from quodeq.services.dashboard_trend import build_accumulated_trend
from tests.services._dashboard_fixtures import _make_run

_MAJOR, _MINOR = "major", "minor"


def _dim(name: str, reqs: list[tuple[str, str]]) -> DimensionResult:
    violations = [
        Finding(practice_id="P", verdict="violation", file="a.py", line=i, req=req,
                severity=sev, dimension=name)
        for i, (req, sev) in enumerate(reqs)
    ]
    return DimensionResult(dimension=name, overall_score="8.0/10", overall_grade="Good",
                           violations=violations)


def test_trend_row_carries_majors_violations_and_open_types() -> None:
    runs = [_make_run("r1", "2026-09-26")]
    dims = {"r1": [_dim("maintainability", [("M-MDF-1", _MINOR), ("M-MDF-1", _MINOR),
                                            ("M-MOD-3", _MAJOR)])]}
    (row,) = build_accumulated_trend(runs, lambda rid: dims[rid])
    assert (row["violations"], row["majors"], row["openTypes"]) == (3, 1, 2)
    (detail,) = row["dimensionDetails"]
    assert (detail["violations"], detail["majors"], detail["openTypes"]) == (3, 1, 2)


def test_trend_counts_zero_for_a_clean_dimension() -> None:
    runs = [_make_run("r0", "2026-09-25")]
    (row,) = build_accumulated_trend(runs, lambda rid: [_dim("security", [])])
    assert (row["violations"], row["majors"], row["openTypes"]) == (0, 0, 0)
    assert row["dimensionDetails"][0]["openTypes"] == 0
