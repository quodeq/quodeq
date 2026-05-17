"""Tests for quodeq.services.accumulated — cross-run aggregation logic."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from quodeq.core.types import DimensionResult
from quodeq.core.types.mappers import parse_dimension_result
from quodeq.services.accumulated import (
    _aggregate_severity_counts,
    _compute_accumulated_scores,
    _compute_accumulated_trends,
    numeric_average,
    _read_all_run_data,
    compute_accumulated,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dim(name: str, score: str = "7.5", grade: str = "B", **extra: Any) -> DimensionResult:
    """Build a minimal DimensionResult."""
    raw: dict[str, Any] = {"dimension": name, "overallScore": score, "overallGrade": grade, **extra}
    return parse_dimension_result(raw)


def _write_eval(path: Path, dim_name: str, score: str = "7.5", grade: str = "B", **extra: Any) -> None:
    """Write a minimal evaluation JSON file for a dimension."""
    path.mkdir(parents=True, exist_ok=True)
    data = {"dimension": dim_name, "overallScore": score, "overallGrade": grade, "principles": [], "violations": [], "compliance": [], **extra}
    (path / f"{dim_name}.json").write_text(json.dumps(data))


def _write_evidence(path: Path, dim_name: str, discipline: str = "typescript") -> None:
    """Write a minimal evidence JSON file."""
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{dim_name}_evidence.json").write_text(json.dumps({"dimension": dim_name, "discipline": discipline}))


def _setup_project(tmp_path: Path, project: str, runs: list[tuple[str, list[DimensionResult]]]) -> Path:
    """Set up a project directory with the given runs and dimensions.

    *runs* is a list of (run_id, [DimensionResult, ...]) pairs, newest first.
    Returns the reports root path.
    """
    reports_root = tmp_path / "evaluations"
    for run_id, dims in runs:
        run_dir = reports_root / project / run_id
        for dim in dims:
            dim_name = dim.dimension
            eval_dir = run_dir / "evaluation"
            _write_eval(eval_dir, dim_name, dim.overall_score or "7.5", dim.overall_grade or "B")
            evidence_dir = run_dir / "evidence"
            _write_evidence(evidence_dir, dim_name)
        evidence_dir = run_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "manifest.json").write_text("{}")
        (run_dir / "scan.json").write_text("{}")
    return reports_root


# ---------------------------------------------------------------------------
# _numeric_average
# ---------------------------------------------------------------------------

class TestNumericAverage:
    def test_computes_average(self):
        """Two dimensions with scores 8.0 and 6.0 should average to 7.0."""
        dims = [_dim("a", "8.0"), _dim("b", "6.0")]
        assert numeric_average(dims) == 7.0

    def test_returns_none_for_empty(self):
        assert numeric_average([]) is None

    def test_skips_none_scores(self):
        dims = [_dim("a", "8.0"), DimensionResult(dimension="b", overall_score=None)]
        assert numeric_average(dims) == 8.0

    def test_handles_grade_strings(self):
        dims = [_dim("a", "A"), _dim("b", "9.0")]
        # "A" is not numeric, should be skipped
        result = numeric_average(dims)
        assert result == 9.0

    def test_all_non_numeric_returns_none(self):
        dims = [_dim("a", "A"), _dim("b", "B+")]
        assert numeric_average(dims) is None

    def test_single_dimension(self):
        dims = [_dim("a", "10.0")]
        assert numeric_average(dims) == 10.0


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

    def test_excludes_cancelled_run_from_per_dim_latest(self, tmp_path: Path):
        # The newer run is cancelled — its per-dim eval files exist but
        # represent partial work that doesn't agree with the headline. The
        # accumulated cards should pick from the older complete run instead,
        # so the headline (averaged from the same dims) matches the cards.
        reports_root = _setup_project(tmp_path, "proj", [
            ("run2", [_dim("security", "9.5", "A"), _dim("maintainability", "9.5", "A")]),
            ("run1", [_dim("security", "7.0", "B"), _dim("maintainability", "8.0", "B")]),
        ])
        # Mark run2 as cancelled by writing status.json.
        (reports_root / "proj" / "run2" / "status.json").write_text(
            json.dumps({"state": "cancelled"}),
        )
        result = compute_accumulated(str(reports_root), "proj", None)
        assert result is not None
        scores = {d["dimension"]: d["overallScore"] for d in result["dimensions"]}
        # Both should fall through to run1 (the latest complete run), not run2.
        assert scores == {"security": "7.0", "maintainability": "8.0"}
        assert result["summary"]["numericAverage"] == 7.5  # avg(7.0, 8.0)

    def test_excludes_in_progress_run_from_overview(self, tmp_path: Path):
        # A dim scored inside an in-progress run must NOT leak into the
        # overview cards — the umbrella run hasn't terminated. The cards
        # wait until the run reaches a terminal state and fall through
        # to the previous complete run for every dim in the meantime.
        # The user can still inspect the running run's already-scored
        # dims by clicking through the (running) row in history.
        #
        # ``list_runs`` derives in_progress from a live ``.pid`` file
        # (status.json with state="running" doesn't trigger in_progress
        # — only a live PID does). The test process's own pid is
        # guaranteed alive for the duration of the call.
        import os
        reports_root = _setup_project(tmp_path, "proj", [
            ("run2", [_dim("usability", "9.5", "A")]),
            ("run1", [_dim("usability", "7.0", "B"), _dim("flexibility", "6.0", "C")]),
        ])
        (reports_root / "proj" / "run2" / ".pid").write_text(str(os.getpid()))
        result = compute_accumulated(str(reports_root), "proj", None)
        assert result is not None
        scores = {d["dimension"]: d["overallScore"] for d in result["dimensions"]}
        # Both dims fall through to run1; run2's mid-flight 9.5 is hidden.
        assert scores == {"usability": "7.0", "flexibility": "6.0"}

    def test_falls_back_when_all_runs_cancelled(self, tmp_path: Path):
        # If every run is cancelled (fresh project, all attempts crashed), we
        # still want to render *something* rather than a blank dashboard, so
        # the filter falls back to all runs.
        reports_root = _setup_project(tmp_path, "proj", [
            ("run1", [_dim("security", "6.0", "C")]),
        ])
        (reports_root / "proj" / "run1" / "status.json").write_text(
            json.dumps({"state": "cancelled"}),
        )
        result = compute_accumulated(str(reports_root), "proj", None)
        assert result is not None
        assert result["dimensions"][0]["overallScore"] == "6.0"

    def test_first_run_in_progress_yields_empty_overview(self, tmp_path: Path):
        # Fresh project, only run is in_progress: overview is empty because
        # no run has terminated yet. The user sees a blank dashboard until
        # the run finishes — by design. (Previously the overview leaked
        # mid-flight scores; now it waits for terminal status.)
        import os
        reports_root = _setup_project(tmp_path, "proj", [
            ("run1", [_dim("performance", "9.5", "A")]),
        ])
        (reports_root / "proj" / "run1" / ".pid").write_text(str(os.getpid()))

        result = compute_accumulated(str(reports_root), "proj", None)
        # Project exists so result is non-None, but no eligible dims.
        assert result is not None
        assert result["dimensions"] == []
        assert result["summary"]["dimensionCount"] == 0
