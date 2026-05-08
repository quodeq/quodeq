"""Tests for the central dim_resolution module.

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

import json
from pathlib import Path
from unittest.mock import patch

from quodeq.data.fs.report_parser import RunInfo
from quodeq.services.dim_resolution import (
    DimResolution,
    is_eligible_for_chart_bar,
    is_eligible_for_default_view,
    is_trustable_run,
    is_visible_in_history,
    resolve_latest_per_dim,
)


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

# Each test gets a unique date per run_id so list_runs can sort newest-first.
_RUN_DATES = {
    "run1": "2026-01-01T10:00:00",
    "run2": "2026-02-01T10:00:00",
    "run3": "2026-03-01T10:00:00",
    "r1":   "2026-01-01T10:00:00",
    "r2":   "2026-02-01T10:00:00",
}


def _ensure_run_dir(project_dir: Path, run_id: str) -> Path:
    """Create a run dir with the manifest.json that ``list_runs`` needs to
    register the run as a project entry."""
    run_dir = project_dir / run_id
    evidence = run_dir / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "manifest.json").write_text("{}")
    return run_dir


def _write_eval(
    project_dir: Path, run_id: str, dim_id: str,
    *, files_read: int = 100, score: str = "8.0/10", grade: str = "Good",
) -> None:
    _ensure_run_dir(project_dir, run_id)
    eval_dir = project_dir / run_id / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / f"{dim_id}.json").write_text(json.dumps({
        "dimension": dim_id,
        "date": _RUN_DATES.get(run_id, "2026-01-01T10:00:00"),
        "filesRead": files_read,
        "overallScore": score,
        "overallGrade": grade,
    }))


def _write_status(project_dir: Path, run_id: str, *, state: str) -> None:
    run_dir = project_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "status.json").write_text(json.dumps({"state": state}))


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


# ---------------------------------------------------------------------------
# is_visible_in_history
# ---------------------------------------------------------------------------

class TestIsVisibleInHistory:
    def _run(self, run_id: str, status: str = "complete") -> RunInfo:
        return RunInfo(run_id=run_id, date_iso="2026-04-27", date_label="Apr 27", status=status)

    def test_visible_when_run_has_trustworthy_eval(self, tmp_path: Path):
        proj_dir = tmp_path / "proj"
        _write_eval(proj_dir, "r1", "security")
        assert is_visible_in_history(tmp_path, "proj", self._run("r1")) is True

    def test_hidden_when_failed(self, tmp_path: Path):
        proj_dir = tmp_path / "proj"
        _write_eval(proj_dir, "r1", "security")
        assert is_visible_in_history(tmp_path, "proj", self._run("r1", "failed")) is False

    def test_hidden_when_no_evals(self, tmp_path: Path):
        proj_dir = tmp_path / "proj"
        (proj_dir / "r1").mkdir(parents=True)
        assert is_visible_in_history(tmp_path, "proj", self._run("r1", "cancelled")) is False

    def test_hidden_when_only_zero_coverage_evals(self, tmp_path: Path):
        # Cancelled run with stub eval files — nothing useful to show.
        proj_dir = tmp_path / "proj"
        _write_eval(proj_dir, "r1", "security", files_read=0)
        assert is_visible_in_history(tmp_path, "proj", self._run("r1", "cancelled")) is False

    def test_visible_when_cancelled_with_partial_real_data(self, tmp_path: Path):
        # Cancelled run that completed at least one dim cleanly — surface
        # it in history with the partial chip the UI already supports.
        proj_dir = tmp_path / "proj"
        _write_eval(proj_dir, "r1", "security", files_read=500)
        assert is_visible_in_history(tmp_path, "proj", self._run("r1", "cancelled")) is True

    def test_visible_when_in_progress_with_partial_data(self, tmp_path: Path):
        proj_dir = tmp_path / "proj"
        _write_eval(proj_dir, "r1", "security", files_read=500)
        assert is_visible_in_history(tmp_path, "proj", self._run("r1", "in_progress")) is True


# ---------------------------------------------------------------------------
# is_eligible_for_chart_bar
# ---------------------------------------------------------------------------

class TestSharedTrustPredicates:
    """Pin the two run-state predicates that are the shared source of truth
    for ``accumulated._compute_result`` and ``dashboard._resolve_selected_run``.
    Drift between these two predicates is what produces the "headline says
    one thing, cards say another" class of bug.
    """

    def test_is_trustable_run_includes_complete_in_progress_cancelled(self):
        # The broader rule — used by history visibility. Cancelled is in
        # because a cancelled run can still have dims that finished cleanly.
        assert is_trustable_run("complete") is True
        assert is_trustable_run("in_progress") is True
        assert is_trustable_run("cancelled") is True

    def test_is_trustable_run_excludes_failed(self):
        assert is_trustable_run("failed") is False

    def test_is_eligible_for_default_view_includes_only_complete(self):
        # The strictest rule — used by overview cards / headline. Only
        # terminal-and-trustworthy runs count: ``complete``. in_progress
        # is excluded so partial mid-run dims don't leak into the cards;
        # cancelled is excluded because of partial-coverage stub evals.
        assert is_eligible_for_default_view("complete") is True

    def test_is_eligible_for_default_view_excludes_in_progress_cancelled_failed(self):
        assert is_eligible_for_default_view("in_progress") is False
        assert is_eligible_for_default_view("cancelled") is False
        assert is_eligible_for_default_view("failed") is False


class TestIsEligibleForChartBar:
    def _run(self, run_id: str, status: str = "complete") -> RunInfo:
        return RunInfo(run_id=run_id, date_iso="2026-04-27", date_label="Apr 27", status=status)

    def test_complete_with_all_dims_eligible(self, tmp_path: Path):
        proj_dir = tmp_path / "proj"
        _write_eval(proj_dir, "r1", "security")
        _write_eval(proj_dir, "r1", "reliability")
        run = self._run("r1")
        assert is_eligible_for_chart_bar(
            tmp_path, "proj", run, configured_dims=["security", "reliability"],
        ) is True

    def test_complete_missing_a_dim_not_eligible(self, tmp_path: Path):
        # Snapshot semantics: every configured dim must have contributed
        # for the bar to mean what the chart claims it means.
        proj_dir = tmp_path / "proj"
        _write_eval(proj_dir, "r1", "security")
        run = self._run("r1")
        assert is_eligible_for_chart_bar(
            tmp_path, "proj", run, configured_dims=["security", "reliability"],
        ) is False

    def test_in_progress_with_all_dims_eligible(self, tmp_path: Path):
        # A snapshot's a snapshot — if every configured dim is scored,
        # the bar is meaningful regardless of the umbrella run state.
        proj_dir = tmp_path / "proj"
        _write_eval(proj_dir, "r1", "security")
        _write_eval(proj_dir, "r1", "reliability")
        run = self._run("r1", "in_progress")
        assert is_eligible_for_chart_bar(
            tmp_path, "proj", run, configured_dims=["security", "reliability"],
        ) is True

    def test_cancelled_never_eligible(self, tmp_path: Path):
        # Even if a cancelled run happens to have all dims scored, treat
        # it as untrustworthy for the chart — the bar implies the run
        # finished its lifecycle, not just its dims.
        proj_dir = tmp_path / "proj"
        _write_eval(proj_dir, "r1", "security")
        _write_eval(proj_dir, "r1", "reliability")
        run = self._run("r1", "cancelled")
        assert is_eligible_for_chart_bar(
            tmp_path, "proj", run, configured_dims=["security", "reliability"],
        ) is False

    def test_failed_never_eligible(self, tmp_path: Path):
        proj_dir = tmp_path / "proj"
        _write_eval(proj_dir, "r1", "security")
        run = self._run("r1", "failed")
        assert is_eligible_for_chart_bar(
            tmp_path, "proj", run, configured_dims=["security"],
        ) is False

    def test_zero_coverage_eval_does_not_count_toward_coverage(self, tmp_path: Path):
        # A stub eval (filesRead=0) is the same as a missing eval for the
        # purposes of "did this dim contribute to the snapshot".
        proj_dir = tmp_path / "proj"
        _write_eval(proj_dir, "r1", "security")
        _write_eval(proj_dir, "r1", "reliability", files_read=0)
        run = self._run("r1")
        assert is_eligible_for_chart_bar(
            tmp_path, "proj", run, configured_dims=["security", "reliability"],
        ) is False
