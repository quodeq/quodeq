"""Tests for quodeq.provider.accumulated — cross-run aggregation logic."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from quodeq.provider.accumulated import (
    _aggregate_severity_counts,
    _compute_accumulated_scores,
    _compute_accumulated_trends,
    _find_previous_run,
    numeric_average,
    _read_all_run_data,
    compute_accumulated,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dim(name: str, score: str = "7.5", grade: str = "B", **extra: Any) -> dict[str, Any]:
    """Build a minimal dimension dict."""
    return {"dimension": name, "overallScore": score, "overallGrade": grade, **extra}


def _write_eval(path: Path, dim_name: str, score: str = "7.5", grade: str = "B", **extra: Any) -> None:
    """Write a minimal evaluation JSON file for a dimension."""
    path.mkdir(parents=True, exist_ok=True)
    data = {"dimension": dim_name, "overallScore": score, "overallGrade": grade, "principles": [], "violations": [], "compliance": [], **extra}
    (path / f"{dim_name}.json").write_text(json.dumps(data))


def _write_evidence(path: Path, dim_name: str, discipline: str = "typescript") -> None:
    """Write a minimal evidence JSON file."""
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{dim_name}_evidence.json").write_text(json.dumps({"dimension": dim_name, "discipline": discipline}))


def _setup_project(tmp_path: Path, project: str, runs: list[tuple[str, list[dict]]]) -> Path:
    """Set up a project directory with the given runs and dimensions.

    *runs* is a list of (run_id, [dim_dict, ...]) pairs, newest first.
    Returns the reports root path.
    """
    reports_root = tmp_path / "evaluations"
    for run_id, dims in runs:
        for dim in dims:
            dim_name = dim["dimension"]
            eval_dir = reports_root / project / run_id / "evaluation"
            _write_eval(eval_dir, dim_name, dim.get("overallScore", "7.5"), dim.get("overallGrade", "B"))
            evidence_dir = reports_root / project / run_id / "evidence"
            _write_evidence(evidence_dir, dim_name)
    return reports_root


# ---------------------------------------------------------------------------
# _numeric_average
# ---------------------------------------------------------------------------

class TestNumericAverage:
    def test_computes_average(self):
        dims = [_dim("a", "8.0"), _dim("b", "6.0")]
        assert numeric_average(dims) == 7.0

    def test_returns_none_for_empty(self):
        assert numeric_average([]) is None

    def test_skips_none_scores(self):
        dims = [_dim("a", "8.0"), {"dimension": "b", "overallScore": None}]
        assert numeric_average(dims) == 8.0

    def test_handles_grade_strings(self):
        dims = [_dim("a", "A"), _dim("b", "9.0")]
        # "A" is not numeric, should be skipped
        result = numeric_average(dims)
        assert result == 9.0


# ---------------------------------------------------------------------------
# _aggregate_severity_counts
# ---------------------------------------------------------------------------

class TestAggregateSeverityCounts:
    def test_sums_across_dimensions(self):
        dims = [
            _dim("a", totals={"violationCount": 3, "complianceCount": 5, "severity": {"critical": 1, "major": 1, "minor": 1}}),
            _dim("b", totals={"violationCount": 2, "complianceCount": 1, "severity": {"critical": 0, "major": 2, "minor": 0}}),
        ]
        result = _aggregate_severity_counts(dims)
        assert result["totalViolations"] == 5
        assert result["totalCompliance"] == 6
        assert result["critical"] == 1
        assert result["major"] == 3
        assert result["minor"] == 1

    def test_handles_missing_totals(self):
        dims = [_dim("a")]
        result = _aggregate_severity_counts(dims)
        assert result["totalViolations"] == 0

    def test_empty_list(self):
        result = _aggregate_severity_counts([])
        assert result["totalViolations"] == 0
        assert result["critical"] == 0


# ---------------------------------------------------------------------------
# _find_previous_run
# ---------------------------------------------------------------------------

class TestFindPreviousRun:
    def test_finds_previous(self):
        runs = ["run3", "run2", "run1"]
        all_data = {
            "run3": [_dim("maintainability")],
            "run2": [_dim("security")],
            "run1": [_dim("maintainability", "6.0")],
        }
        result = _find_previous_run("maintainability", "run3", runs, all_data)
        assert result is not None
        assert result["runId"] == "run1"

    def test_returns_none_when_no_previous(self):
        runs = ["run1"]
        all_data = {"run1": [_dim("maintainability")]}
        assert _find_previous_run("maintainability", "run1", runs, all_data) is None

    def test_returns_none_for_unknown_run(self):
        assert _find_previous_run("x", "unknown", ["run1"], {"run1": []}) is None


# ---------------------------------------------------------------------------
# compute_accumulated (integration)
# ---------------------------------------------------------------------------

class TestComputeAccumulated:
    def test_single_run(self, tmp_path: Path):
        reports_root = _setup_project(tmp_path, "proj", [
            ("run1", [_dim("maintainability", "8.0", "A")]),
        ])
        result = compute_accumulated(str(reports_root), "proj", None)
        assert result is not None
        assert result["project"] == "proj"
        assert len(result["dimensions"]) == 1
        assert result["summary"]["dimensionCount"] == 1
        assert result["summary"]["numericAverage"] == 8.0

    def test_multiple_runs_picks_latest(self, tmp_path: Path):
        # run2 is newer (sorted by name descending)
        reports_root = _setup_project(tmp_path, "proj", [
            ("run2", [_dim("maintainability", "9.0", "A")]),
            ("run1", [_dim("maintainability", "6.0", "C")]),
        ])
        result = compute_accumulated(str(reports_root), "proj", None)
        assert result is not None
        # Latest should be run2 with score 9.0
        dim = result["dimensions"][0]
        assert dim["overallScore"] == "9.0"

    def test_nonexistent_project_returns_none(self, tmp_path: Path):
        assert compute_accumulated(str(tmp_path), "nonexistent", None) is None

    def test_as_of_filters_runs(self, tmp_path: Path):
        reports_root = _setup_project(tmp_path, "proj", [
            ("run3", [_dim("maintainability", "9.0")]),
            ("run2", [_dim("maintainability", "7.0")]),
            ("run1", [_dim("maintainability", "5.0")]),
        ])
        result = compute_accumulated(str(reports_root), "proj", "run2")
        assert result is not None
        # Only run2 and run1 included
        dim = result["dimensions"][0]
        assert dim["overallScore"] == "7.0"

    def test_as_of_unknown_run_returns_none(self, tmp_path: Path):
        reports_root = _setup_project(tmp_path, "proj", [
            ("run1", [_dim("maintainability")]),
        ])
        assert compute_accumulated(str(reports_root), "proj", "unknown") is None

    def test_severity_summary(self, tmp_path: Path):
        reports_root = _setup_project(tmp_path, "proj", [
            ("run1", [_dim("maintainability", "7.0")]),
        ])
        result = compute_accumulated(str(reports_root), "proj", None)
        assert "severity" in result["summary"]
        assert "critical" in result["summary"]["severity"]
