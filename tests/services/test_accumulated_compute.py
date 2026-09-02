"""Tests for quodeq.services.accumulated — compute_accumulated (integration).

Split from test_accumulated.py. Shared builders live in
tests/services/_accumulated_fixtures.py.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from quodeq.services.accumulated import compute_accumulated

from tests.services._accumulated_fixtures import _dim, _setup_project


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
        reports_root = _setup_project(tmp_path, "proj", [
            ("run1", [_dim("performance", "9.5", "A")]),
        ])
        (reports_root / "proj" / "run1" / ".pid").write_text(str(os.getpid()))

        result = compute_accumulated(str(reports_root), "proj", None)
        # Project exists so result is non-None, but no eligible dims.
        assert result is not None
        assert result["dimensions"] == []
        assert result["summary"]["dimensionCount"] == 0


class TestFallbackExcludesFailed:
    def test_failed_only_project_yields_empty_overview(self, tmp_path: Path):
        # A failed run's partial evals must not masquerade as the project
        # grade: the run errored before producing trustworthy data (this is
        # what _compute_result's docstring always claimed; the fallback
        # code included failed runs anyway).
        reports_root = _setup_project(tmp_path, "proj", [
            ("run1", [_dim("security", "3.0", "D")]),
        ])
        (reports_root / "proj" / "run1" / "status.json").write_text(
            json.dumps({"state": "failed"}),
        )
        result = compute_accumulated(str(reports_root), "proj", None)
        assert result is not None
        assert result["dimensions"] == []
        assert result["summary"]["dimensionCount"] == 0

    def test_fallback_prefers_cancelled_and_skips_failed(self, tmp_path: Path):
        reports_root = _setup_project(tmp_path, "proj", [
            ("run2", [_dim("security", "9.0", "A")]),
            ("run1", [_dim("security", "6.0", "C")]),
        ])
        (reports_root / "proj" / "run2" / "status.json").write_text(
            json.dumps({"state": "failed"}),
        )
        (reports_root / "proj" / "run1" / "status.json").write_text(
            json.dumps({"state": "cancelled"}),
        )
        result = compute_accumulated(str(reports_root), "proj", None)
        assert result is not None
        assert result["dimensions"][0]["overallScore"] == "6.0"
