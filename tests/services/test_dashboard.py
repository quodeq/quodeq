"""Tests for quodeq.provider.dashboard — dashboard construction logic."""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from quodeq.data.fs.report_parser import RunInfo
from quodeq.core.types import DimensionResult, DimensionSummary
from quodeq.services.dashboard import (
    _collect_previous_scores,
    _enrich_dimensions_with_trend,
    build_dashboard,
)
from quodeq.services._dashboard_trend import build_accumulated_trend as _build_accumulated_trend
from quodeq.services._dashboard_stale import collect_stale_dimensions as _collect_stale_dimensions


def _make_run(run_id: str, date_iso: str = "2024-01-01") -> RunInfo:
    return RunInfo(run_id=run_id, date_iso=date_iso, date_label=date_iso)


def _dim(name: str, grade: str = "B", score: str = "7.0") -> DimensionResult:
    return DimensionResult(dimension=name, overall_grade=grade, overall_score=score)


class TestCollectPreviousScores:
    def test_finds_previous_for_matching_dimension(self):
        runs = [_make_run("r1"), _make_run("r2")]
        fetcher = lambda rid: [_dim("security", "A", "9.0")] if rid == "r2" else []
        result = _collect_previous_scores(runs, 0, {"security"}, fetcher)
        assert "security" in result
        assert result["security"].overall_grade == "A"

    def test_skips_na_grades(self):
        runs = [_make_run("r1"), _make_run("r2")]
        fetcher = lambda rid: [_dim("security", "NA", "0")] if rid == "r2" else []
        result = _collect_previous_scores(runs, 0, {"security"}, fetcher)
        assert result == {}

    def test_ignores_dimensions_not_in_selected(self):
        runs = [_make_run("r1"), _make_run("r2")]
        fetcher = lambda rid: [_dim("perf")] if rid == "r2" else []
        result = _collect_previous_scores(runs, 0, {"security"}, fetcher)
        assert result == {}


class TestCollectStaleDimensions:
    def test_detects_stale_from_older_run(self):
        runs = [_make_run("r1"), _make_run("r2")]
        fetcher = lambda rid: [_dim("perf")] if rid == "r2" else []
        stale, _ = _collect_stale_dimensions(runs, 0, {"security"}, fetcher)
        assert len(stale) == 1
        assert stale[0].dimension == "perf"
        assert stale[0].stale is True

    def test_no_stale_when_all_present(self):
        runs = [_make_run("r1"), _make_run("r2")]
        fetcher = lambda rid: [_dim("security")]
        stale, _ = _collect_stale_dimensions(runs, 0, {"security"}, fetcher)
        assert stale == []

    def test_empty_runs_returns_empty(self):
        stale, _ = _collect_stale_dimensions([], 0, {"security"}, lambda rid: [])
        assert stale == []


class TestCollectPreviousScoresEdgeCases:
    def test_single_run_returns_empty(self):
        runs = [_make_run("r1")]
        fetcher = lambda rid: [_dim("security", "A", "9.0")]
        result = _collect_previous_scores(runs, 0, {"security"}, fetcher)
        assert result == {}


class TestEnrichDimensionsWithTrend:
    def test_adds_trend_fields(self):
        dims = [_dim("security", "B", "7.0")]
        previous = {"security": DimensionResult(dimension="security", overall_score="6.0", run_id="r0")}
        result = _enrich_dimensions_with_trend(dims, previous)
        assert len(result) == 1
        assert result[0].trend is not None
        assert result[0].previous_run_id == "r0"
        assert result[0].previous_score == "6.0"

    def test_no_previous(self):
        dims = [_dim("security")]
        result = _enrich_dimensions_with_trend(dims, {})
        assert result[0].previous_run_id is None


class TestBuildAccumulatedTrend:
    def test_accumulates_across_runs(self):
        runs = [_make_run("r2", "2024-02-01"), _make_run("r1", "2024-01-01")]
        fetcher = lambda rid: [_dim("security", "B", "7.0")]
        trend = _build_accumulated_trend(runs, fetcher)
        assert len(trend) == 2
        assert trend[0]["runId"] == "r2"
        assert trend[1]["runId"] == "r1"
        assert trend[0]["numericAverage"] is not None


class TestBuildDashboard:
    def test_raises_when_no_runs(self, tmp_path):
        with patch("quodeq.services.dashboard.list_runs", return_value=[]):
            with pytest.raises(FileNotFoundError, match="No runs found"):
                build_dashboard(str(tmp_path), "proj", "latest")

    def test_raises_when_run_not_found(self, tmp_path):
        with patch("quodeq.services.dashboard.list_runs", return_value=[_make_run("r1")]):
            with pytest.raises(FileNotFoundError, match="Run not found"):
                build_dashboard(str(tmp_path), "proj", "nonexistent")

    def test_builds_dashboard_for_latest(self, tmp_path):
        run = _make_run("r1", "2024-01-01")
        dims = [_dim("security", "B", "7.0")]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)
        with (
            patch("quodeq.services.dashboard.list_runs", return_value=[run]),
            patch("quodeq.services.dashboard.read_run_data", return_value=dims),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            result = build_dashboard(str(tmp_path), "proj", "latest")
        assert result["project"] == "proj"
        assert result["selectedRun"]["runId"] == "r1"
        assert len(result["dimensions"]) == 1
        assert "trend" in result
