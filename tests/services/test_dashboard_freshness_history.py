"""Tests for quodeq.services.dashboard — in-progress freshness through the
full build_dashboard history path.

Split from test_dashboard_freshness.py (further split out to stay under
the file-size cap). Shared builders live in
tests/services/_dashboard_fixtures.py.
"""
from __future__ import annotations

from unittest.mock import patch

from quodeq.core.types import DimensionSummary
from quodeq.data.fs.report_parser import RunInfo
from quodeq.services.dashboard import build_dashboard
from tests.services._dashboard_fixtures import _dim


class TestInProgressFreshnessThroughDashboard:
    """After the trend-cache perf fix the History trend/previous/stale path is
    served by the cache-backed SCALAR fetcher. This pins that an in_progress
    history run is still read FRESH on every dashboard request: its scalar set
    grows as dims finish mid-run, and the fix must NOT persist a partial set
    (which would strand a stale trend point served forever after the run ends).
    """

    def test_in_progress_history_run_read_fresh_each_call(self, tmp_path, monkeypatch):
        # Isolate the read-through score cache so a persisted row from another
        # test can't mask a regression here.
        monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "score_cache.db"))

        selected = RunInfo(run_id="r-sel", date_iso="2024-02-01", date_label="2024-02-01", status="complete")
        running = RunInfo(run_id="r-run", date_iso="2024-01-01", date_label="2024-01-01", status="in_progress")
        runs = [selected, running]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)

        # The in_progress run grows from 1 dim to 2 between the two dashboard
        # calls (a dim finished mid-run). Scalar reads fall back to the runs-
        # module read_run_data for these no-db tmp runs.
        run_call_count = {"r-run": 0}

        def history_read(_root, _project, run_id):
            if run_id == "r-run":
                run_call_count["r-run"] += 1
                if run_call_count["r-run"] == 1:
                    return [_dim("security", "B", "7.0")]
                return [_dim("security", "B", "7.0"), _dim("performance", "A", "9.0")]
            return [_dim("usability", "A", "9.5")]

        from quodeq.services.dashboard import clear_shared_dimension_cache
        clear_shared_dimension_cache()

        with (
            patch("quodeq.services.dashboard.list_runs", return_value=runs),
            patch("quodeq.services.dashboard.read_run_data", side_effect=history_read),
            patch("quodeq.data.fs.report_parser.runs.read_run_data", side_effect=history_read),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            first = build_dashboard(str(tmp_path), "proj-ip", "r-sel")
            second = build_dashboard(str(tmp_path), "proj-ip", "r-sel")

        # The in_progress run's trend point reflects the GROWN dim set on the
        # second call -- proof it was re-read fresh, not served from a persisted
        # partial (which would have frozen it at 1 dim forever).
        def running_point(dash):
            return next(p for p in dash["trend"] if p["runId"] == "r-run")

        assert running_point(first)["dimensionsCount"] == 1
        assert running_point(second)["dimensionsCount"] == 2, (
            "in_progress history run must be re-read fresh each call, not "
            "served from a stale persisted partial"
        )
        # And the in_progress run was read on BOTH calls (never cache-served).
        assert run_call_count["r-run"] == 2
