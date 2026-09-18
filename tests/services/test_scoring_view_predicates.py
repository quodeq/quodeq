"""Tests for scoring_view run-state predicates: history visibility, chart-bar eligibility, trust checks."""
from __future__ import annotations

from pathlib import Path

from quodeq.data.fs.report_parser import RunInfo
from quodeq.services.scoring_view import (
    is_eligible_for_chart_bar,
    is_eligible_for_default_view,
    is_trustable_run,
    is_visible_in_history,
)
from tests.services._scoring_view_fixtures import _write_eval


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


# ---------------------------------------------------------------------------
# #356 — _is_trustworthy_eval must not raise on non-dict eval_data
# ---------------------------------------------------------------------------

class TestIsTrustworthyEvalNonDict:
    def test_list_eval_data_returns_false(self) -> None:
        from quodeq.services.scoring_view._resolution import _is_trustworthy_eval
        assert _is_trustworthy_eval([{"filesRead": 100}]) is False

    def test_string_eval_data_returns_false(self) -> None:
        from quodeq.services.scoring_view._resolution import _is_trustworthy_eval
        assert _is_trustworthy_eval("filesRead: 100") is False

    def test_int_eval_data_returns_false(self) -> None:
        from quodeq.services.scoring_view._resolution import _is_trustworthy_eval
        assert _is_trustworthy_eval(42) is False

    def test_none_eval_data_returns_false(self) -> None:
        from quodeq.services.scoring_view._resolution import _is_trustworthy_eval
        assert _is_trustworthy_eval(None) is False

    def test_valid_dict_with_files_read_returns_true(self) -> None:
        from quodeq.services.scoring_view._resolution import _is_trustworthy_eval
        assert _is_trustworthy_eval({"filesRead": 10}) is True
