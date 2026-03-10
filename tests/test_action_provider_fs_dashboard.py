"""Tests for action_provider_fs_dashboard — dashboard building and cross-run logic."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from quodeq.provider.dashboard import (
    _collect_previous_scores,
    _collect_stale_dimensions,
    _enrich_dimensions_with_trend,
    _build_accumulated_trend,
    build_dashboard,
)
from quodeq.adapters.fs.report_parser.runs import RunInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_eval(eval_dir: Path, dimension: str, score: str, grade: str, date: str = "2026-03-01") -> None:
    """Write a minimal evaluation JSON file for a single dimension."""
    report = {
        "dimension": dimension,
        "overallScore": score,
        "overallGrade": grade,
        "date": date,
        "principles": [],
        "violations": [],
        "compliance": [],
        "totals": {"violationCount": 0, "complianceCount": 0, "severity": {}},
    }
    (eval_dir / f"{dimension}.json").write_text(json.dumps(report))
    (eval_dir / f"{dimension}_eval.md").write_text("# eval")


def _setup_run(reports_root: Path, project: str, run_id: str, dims: list[tuple[str, str, str]], date: str = "2026-03-01") -> None:
    """Create a run directory with evaluation files for given dimensions."""
    eval_dir = reports_root / project / run_id / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    (reports_root / project / run_id / "evidence").mkdir(parents=True, exist_ok=True)
    for dim_name, score, grade in dims:
        _write_eval(eval_dir, dim_name, score, grade, date)


# ---------------------------------------------------------------------------
# _collect_previous_scores
# ---------------------------------------------------------------------------

class TestCollectPreviousScores:
    def test_finds_previous_for_dimension(self):
        runs = [
            RunInfo("run-2", "2026-03-02", "Mar 02, 2026"),
            RunInfo("run-1", "2026-03-01", "Mar 01, 2026"),
        ]
        selected_index = 0
        selected_dim_names = {"maintainability"}

        def get_run_dimensions(run_id: str) -> list[dict]:
            if run_id == "run-1":
                return [{"dimension": "maintainability", "overallGrade": "Good", "overallScore": "7/10"}]
            return []

        result = _collect_previous_scores(runs, selected_index, selected_dim_names, get_run_dimensions)
        assert "maintainability" in result
        assert result["maintainability"]["overallGrade"] == "Good"

    def test_no_previous_when_single_run(self):
        runs = [RunInfo("run-1", "2026-03-01", "Mar 01, 2026")]
        result = _collect_previous_scores(runs, 0, {"maintainability"}, lambda _: [])
        assert result == {}


# ---------------------------------------------------------------------------
# _collect_stale_dimensions
# ---------------------------------------------------------------------------

class TestCollectStaleDimensions:
    def test_finds_stale_dimensions_from_older_runs(self):
        runs = [
            RunInfo("run-2", "2026-03-02", "Mar 02, 2026"),
            RunInfo("run-1", "2026-03-01", "Mar 01, 2026"),
        ]

        def get_run_dimensions(run_id: str) -> list[dict]:
            if run_id == "run-1":
                return [{"dimension": "security", "overallGrade": "Good", "overallScore": "7/10"}]
            return []

        stale, _prev = _collect_stale_dimensions(runs, 0, {"maintainability"}, get_run_dimensions)
        assert len(stale) == 1
        assert stale[0]["dimension"] == "security"
        assert stale[0]["stale"] is True


# ---------------------------------------------------------------------------
# _enrich_dimensions_with_trend
# ---------------------------------------------------------------------------

class TestEnrichDimensionsWithTrend:
    def test_adds_trend_when_previous_exists(self):
        selected = [{"dimension": "maintainability", "overallScore": "8/10"}]
        previous = {"maintainability": {"overallScore": "6/10", "runId": "run-1"}}
        result = _enrich_dimensions_with_trend(selected, previous)
        assert result[0]["trend"] == "up"
        assert result[0]["previousRunId"] == "run-1"

    def test_trend_none_without_previous(self):
        selected = [{"dimension": "maintainability", "overallScore": "8/10"}]
        result = _enrich_dimensions_with_trend(selected, {})
        assert result[0]["trend"] == "none"


# ---------------------------------------------------------------------------
# _build_accumulated_trend
# ---------------------------------------------------------------------------

class TestBuildAccumulatedTrend:
    def test_builds_trend_across_runs(self):
        runs = [
            RunInfo("run-2", "2026-03-02", "Mar 02, 2026"),
            RunInfo("run-1", "2026-03-01", "Mar 01, 2026"),
        ]

        def get_run_dimensions(run_id: str) -> list[dict]:
            if run_id == "run-1":
                return [{"dimension": "maintainability", "overallScore": "6/10", "overallGrade": "Adequate"}]
            return [{"dimension": "maintainability", "overallScore": "8/10", "overallGrade": "Good"}]

        trend = _build_accumulated_trend(runs, get_run_dimensions)
        assert len(trend) == 2
        assert trend[0]["runId"] == "run-2"
        assert trend[1]["runId"] == "run-1"


# ---------------------------------------------------------------------------
# build_dashboard (integration)
# ---------------------------------------------------------------------------

class TestBuildDashboard:
    def test_builds_dashboard_for_single_run(self, tmp_path):
        project = "proj-uuid"
        _setup_run(tmp_path, project, "run-1", [("maintainability", "7.5/10", "Good")])
        result = build_dashboard(str(tmp_path), project, "latest")
        assert result["project"] == project
        assert len(result["dimensions"]) == 1
        assert result["dimensions"][0]["dimension"] == "maintainability"

    def test_raises_for_missing_project(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            build_dashboard(str(tmp_path), "nonexistent", "latest")

    def test_raises_for_missing_run(self, tmp_path):
        project = "proj-uuid"
        _setup_run(tmp_path, project, "run-1", [("maintainability", "7/10", "Good")])
        with pytest.raises(FileNotFoundError, match="Run not found"):
            build_dashboard(str(tmp_path), project, "nonexistent-run")
