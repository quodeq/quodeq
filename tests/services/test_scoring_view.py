"""Tests for the central scoring_view package.

This module is the single source of truth for which run/dim data should
appear in which view. The tests pin down its three guarantees:

  1. resolve_latest_per_dim returns the freshest *trustworthy* eval per
     dim, with full provenance, and never picks from failed runs or
     zero-coverage stubs.
  2. is_visible_in_history accepts any non-failed run that has at least
     one trustworthy eval — partial work is discoverable.
  3. is_eligible_for_chart_bar is stricter — only runs where every
     configured dim has a trustworthy eval qualify.

Together these make the migration in later phases safe: each call site
can replace its local filter with a documented predicate from this module.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from quodeq.data.fs.report_parser import RunInfo
from quodeq.services.scoring_view import DimResolution, resolve_latest_per_dim
from tests.services._scoring_view_fixtures import _write_eval, _write_status


# ---------------------------------------------------------------------------
# resolve_latest_per_dim
# ---------------------------------------------------------------------------

class TestResolveLatestPerDim:
    def test_picks_newest_complete_run_per_dim(self, tmp_path: Path):
        # Two complete runs, run2 newer; the newer run's score wins for
        # every dim it contains.
        proj_dir = tmp_path / "proj"
        _write_eval(proj_dir, "run2", "security", score="9.0/10")
        _write_eval(proj_dir, "run1", "security", score="6.0/10")
        # No status.json → defaults to "complete" via the run parser.

        result = resolve_latest_per_dim(tmp_path, "proj")
        assert "security" in result
        assert result["security"].overall_score == "9.0/10"
        assert result["security"].run_id == "run2"
        assert result["security"].run_state == "complete"

    def test_falls_through_to_older_run_when_newest_lacks_dim(self, tmp_path: Path):
        # A common scenario: today's run only finished some dims; older
        # complete run carries the rest. Result is a hybrid view, but each
        # card carries provenance so the user knows where it came from.
        proj_dir = tmp_path / "proj"
        _write_eval(proj_dir, "run2", "security", score="9.0/10")
        _write_eval(proj_dir, "run1", "security", score="6.0/10")
        _write_eval(proj_dir, "run1", "flexibility", score="5.0/10")

        result = resolve_latest_per_dim(tmp_path, "proj")
        assert result["security"].run_id == "run2"
        assert result["flexibility"].run_id == "run1"

    def test_excludes_failed_run(self, tmp_path: Path):
        proj_dir = tmp_path / "proj"
        _write_eval(proj_dir, "run2", "security", score="9.0/10")
        _write_status(proj_dir, "run2", state="failed")
        _write_eval(proj_dir, "run1", "security", score="7.0/10")
        # run1 has no status.json → defaults to "complete".

        result = resolve_latest_per_dim(tmp_path, "proj")
        # The freshest trustworthy is run1 — failed run skipped entirely.
        assert result["security"].run_id == "run1"
        assert result["security"].overall_score == "7.0/10"

    def test_excludes_zero_coverage_eval(self, tmp_path: Path):
        # _score_completed_evidence sometimes writes a stub eval at cancel
        # time with filesRead=0 because no findings landed. That stub's
        # score is meaningless and must not be picked over real data.
        proj_dir = tmp_path / "proj"
        _write_eval(proj_dir, "run2", "security", files_read=0, score="9.5/10")
        _write_status(proj_dir, "run2", state="cancelled")
        _write_eval(proj_dir, "run1", "security", files_read=500, score="7.0/10")

        result = resolve_latest_per_dim(tmp_path, "proj")
        assert result["security"].run_id == "run1"
        assert result["security"].files_read == 500

    def test_excludes_in_progress_run_from_default_view(self, tmp_path: Path):
        # A still-running run's already-scored dims must NOT promote to
        # the overview — the umbrella run hasn't terminated, so the
        # overview waits and falls through to the previous complete run.
        # ``in_progress`` is detected upstream via a live PID lookup, which
        # we'd need to fake on disk; mocking ``list_runs`` at its new
        # location in scoring_view._resolution keeps the test focused on
        # the resolution logic.
        proj_dir = tmp_path / "proj"
        _write_eval(proj_dir, "run2", "security", score="9.0/10")
        _write_eval(proj_dir, "run1", "security", score="7.0/10")
        runs_for_mock = [
            RunInfo(run_id="run2", date_iso="2026-02-01T10:00:00", date_label="Feb 1", status="in_progress"),
            RunInfo(run_id="run1", date_iso="2026-01-01T10:00:00", date_label="Jan 1", status="complete"),
        ]
        with patch("quodeq.services.scoring_view._resolution.list_runs", return_value=runs_for_mock):
            result = resolve_latest_per_dim(tmp_path, "proj")
        # run2 (in_progress) skipped; run1 (complete) wins.
        assert result["security"].run_id == "run1"
        assert result["security"].run_state == "complete"
        assert result["security"].overall_score == "7.0/10"

    def test_excludes_cancelled_run_from_default_view(self, tmp_path: Path):
        # Cancelled runs are NOT promoted to overview cards by default —
        # the user didn't intend that stop, so the data shouldn't drive
        # the cards (per the ``is_eligible_for_default_view`` rule). The
        # cancelled run's eval IS still on disk and is_visible_in_history
        # would surface it; resolve_latest_per_dim falls through to the
        # previous complete run for the dim's default-view value.
        proj_dir = tmp_path / "proj"
        _write_eval(proj_dir, "run2", "security", files_read=500, score="9.0/10")
        _write_status(proj_dir, "run2", state="cancelled")
        _write_eval(proj_dir, "run1", "security", score="7.0/10")

        result = resolve_latest_per_dim(tmp_path, "proj")
        # run2 (cancelled) skipped; run1 (default 'complete') wins.
        assert result["security"].run_id == "run1"
        assert result["security"].overall_score == "7.0/10"

    def test_returns_empty_for_missing_project(self, tmp_path: Path):
        assert resolve_latest_per_dim(tmp_path, "nonexistent") == {}

    def test_returns_empty_when_no_trustworthy_evals(self, tmp_path: Path):
        # Run exists but every eval is zero-coverage — nothing to surface.
        proj_dir = tmp_path / "proj"
        _write_eval(proj_dir, "run1", "security", files_read=0)
        assert resolve_latest_per_dim(tmp_path, "proj") == {}

    def test_returns_provenance_with_path_run_state_and_score(self, tmp_path: Path):
        # Round-trip check on the DimResolution shape itself.
        proj_dir = tmp_path / "proj"
        _write_eval(proj_dir, "run1", "security", score="8.4/10", grade="Good")

        result = resolve_latest_per_dim(tmp_path, "proj")
        res = result["security"]
        assert isinstance(res, DimResolution)
        assert res.dim_id == "security"
        assert res.eval_path == proj_dir / "run1" / "evaluation" / "security.json"
        assert res.run_id == "run1"
        assert res.run_state == "complete"
        assert res.files_read == 100
        assert res.overall_score == "8.4/10"
        assert res.overall_grade == "Good"
