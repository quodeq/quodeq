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
    def test_returns_empty_when_no_runs(self, tmp_path):
        with patch("quodeq.services.dashboard.list_runs", return_value=[]):
            result = build_dashboard(str(tmp_path), "proj", "latest")
            assert result["dimensions"] == []
            assert result["selectedRun"] is None

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

    def test_latest_skips_cancelled_runs(self, tmp_path):
        # ``"latest"`` defaults to the most recent fully-completed run so the
        # per-dim cards reflect a coherent run that agrees with the headline.
        # The cancelled run remains reachable via explicit selection.
        cancelled = RunInfo(run_id="r-newest", date_iso="2024-03-01", date_label="2024-03-01", status="cancelled")
        complete = RunInfo(run_id="r-older", date_iso="2024-02-01", date_label="2024-02-01", status="complete")
        dims = [_dim("security", "B", "7.0")]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)
        with (
            patch("quodeq.services.dashboard.list_runs", return_value=[cancelled, complete]),
            patch("quodeq.services.dashboard.read_run_data", return_value=dims),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            result = build_dashboard(str(tmp_path), "proj", "latest")
        assert result["selectedRun"]["runId"] == "r-older"

    def test_latest_falls_back_when_all_cancelled(self, tmp_path):
        # If every run is cancelled, fall back to the newest one rather than
        # refusing to render — the dashboard still needs to show something.
        cancelled1 = RunInfo(run_id="r2", date_iso="2024-03-01", date_label="2024-03-01", status="cancelled")
        cancelled2 = RunInfo(run_id="r1", date_iso="2024-02-01", date_label="2024-02-01", status="cancelled")
        dims = [_dim("security", "B", "7.0")]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)
        with (
            patch("quodeq.services.dashboard.list_runs", return_value=[cancelled1, cancelled2]),
            patch("quodeq.services.dashboard.read_run_data", return_value=dims),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            result = build_dashboard(str(tmp_path), "proj", "latest")
        assert result["selectedRun"]["runId"] == "r2"

    def test_explicit_run_selection_overrides_latest_default(self, tmp_path):
        # Explicit selection by run_id navigates to that run regardless of
        # state — users can still inspect partial runs from the bar chart.
        cancelled = RunInfo(run_id="r-cancelled", date_iso="2024-03-01", date_label="2024-03-01", status="cancelled")
        complete = RunInfo(run_id="r-complete", date_iso="2024-02-01", date_label="2024-02-01", status="complete")
        dims = [_dim("security", "B", "7.0")]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)
        with (
            patch("quodeq.services.dashboard.list_runs", return_value=[cancelled, complete]),
            patch("quodeq.services.dashboard.read_run_data", return_value=dims),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            result = build_dashboard(str(tmp_path), "proj", "r-cancelled")
        assert result["selectedRun"]["runId"] == "r-cancelled"

    def test_shared_run_dim_cache_persists_across_calls(self, tmp_path):
        # Regression: _make_run_dimension_fetcher used to create a fresh LRU
        # cache per call (via create_dimension_cache()), so dashboard requests
        # paid the read_run_data cost on every call — even when the same run
        # had been read seconds earlier. This test asserts that the second
        # build_dashboard call hits the shared module-level cache for at
        # least one historical run, demonstrably eliminating that I/O.
        runs = [
            RunInfo(run_id=f"r{i}", date_iso=f"2024-{i:02d}-01", date_label=f"2024-{i:02d}-01", status="complete")
            for i in range(1, 6)
        ]
        dims = [_dim("security", "B", "7.0")]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)

        # Track every read_run_data call across both invocations.
        read_calls: list[tuple[str, str]] = []

        def tracked_read(_root, project, run_id):
            read_calls.append((project, run_id))
            return dims

        # Reset the shared cache so this test starts from a clean state.
        from quodeq.services.dashboard import _SHARED_RUN_DIM_CACHE
        _SHARED_RUN_DIM_CACHE.clear()

        with (
            patch("quodeq.services.dashboard.list_runs", return_value=runs),
            patch("quodeq.services._cache.read_run_data", side_effect=tracked_read),
            patch("quodeq.services.dashboard.read_run_data", side_effect=tracked_read),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            build_dashboard(str(tmp_path), "proj-shared", "r3")
            calls_after_first = len(read_calls)
            build_dashboard(str(tmp_path), "proj-shared", "r3")
            calls_after_second = len(read_calls)

        # If the cache were per-request (the bug), the second call would do
        # ~the same number of reads as the first. With the shared cache, the
        # second call's reads via _make_run_dimension_fetcher are eliminated.
        assert calls_after_second < calls_after_first * 2, (
            f"Expected shared cache to reduce reads on second call. "
            f"After 1st: {calls_after_first}, after 2nd: {calls_after_second} "
            f"(would be {calls_after_first * 2} with no caching)"
        )

    def test_does_not_crash_when_cancelled_runs_precede_selected(self, tmp_path):
        # Regression: build_dashboard formerly raised IndexError when the
        # selected complete run had cancelled/failed runs above it in the
        # full list, because ctx.index (full-list index) was passed to
        # collect_stale_dimensions / _collect_previous_scores along with
        # `history_runs` (filtered list of scoreable runs only). When
        # ctx.index >= len(history_runs), `history_runs[newer_idx]` blew up.
        cancelled_top = [
            RunInfo(run_id=f"c{i}", date_iso="2024-03-01", date_label="2024-03-01", status="cancelled")
            for i in range(5)
        ]
        selected = RunInfo(run_id="r-selected", date_iso="2024-02-15", date_label="2024-02-15", status="complete")
        complete_below = [
            RunInfo(run_id=f"c-below-{i}", date_iso="2024-02-01", date_label="2024-02-01", status="complete")
            for i in range(2)
        ]
        runs = cancelled_top + [selected] + complete_below
        dims = [_dim("security", "B", "7.0")]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)
        with (
            patch("quodeq.services.dashboard.list_runs", return_value=runs),
            patch("quodeq.services.dashboard.read_run_data", return_value=dims),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            # Must not raise.
            result = build_dashboard(str(tmp_path), "proj", "r-selected")
        assert result["selectedRun"]["runId"] == "r-selected"
