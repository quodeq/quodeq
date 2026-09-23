"""Tests for the pure state predicates.

Pinning the contracts described in scoring_view/README.md so that:

  - ``is_eligible_for_default_view`` is the strictest rule: only ``DONE``
    runs drive the overview cards. ``RUNNING`` and ``CANCELLED`` are both
    excluded — overview waits for the umbrella run to terminate before
    counting any of its dims.
  - ``select_default_view_runs`` / ``select_trend_runs`` are the shared
    run-set selections used across call sites so they cannot drift apart.

A mismatch between any two of these rules is what the package exists to
prevent — these tests fail fast if the rules drift.
"""
from __future__ import annotations

from quodeq.core.run.state import RunState
from quodeq.services.scoring_view import (
    is_eligible_for_default_view,
)


# ---------------------------------------------------------------------------
# is_eligible_for_default_view
# ---------------------------------------------------------------------------

class TestIsEligibleForDefaultView:
    def test_done_is_eligible(self):
        assert is_eligible_for_default_view(RunState.DONE) is True

    def test_running_is_NOT_eligible(self):
        # A running run's already-scored dims are real but the umbrella
        # run hasn't terminated, so they don't count toward the overview
        # yet. Users see those dims on the run-detail page (clicking the
        # running row in history); the overview cards only update when
        # the run reaches a terminal state.
        assert is_eligible_for_default_view(RunState.RUNNING) is False

    def test_cancelled_is_NOT_eligible(self):
        # A signal-cancelled run can have stub or sparse-coverage
        # evals; promoting them to the cards distorts the score the
        # user reads. Excluded from the default view; user can still
        # navigate explicitly.
        assert is_eligible_for_default_view(RunState.CANCELLED) is False

    def test_failed_is_NOT_eligible(self):
        assert is_eligible_for_default_view(RunState.FAILED) is False


class TestSelectDefaultViewRuns:
    """One shared rule for which runs feed the accumulated/default view.

    The Overview (accumulated._compute_result) and the repositories-screen
    project card must consult the same selection or their grades diverge:
    the card used to take the newest run of ANY status while the Overview
    took done-only. And the fallback used to include failed runs,
    letting a partial failed run masquerade as a normal project grade.
    """

    @staticmethod
    def _run(run_id, status):
        from quodeq.data.fs.report_parser.runs import RunInfo
        return RunInfo(run_id=run_id, date_iso="2026-01-01", date_label="Jan 01", status=status)

    def test_done_runs_win(self):
        from quodeq.services.scoring_view import select_default_view_runs
        runs = [
            self._run("r3", RunState.CANCELLED),
            self._run("r2", RunState.DONE),
            self._run("r1", RunState.FAILED),
        ]
        assert [r.run_id for r in select_default_view_runs(runs)] == ["r2"]

    def test_fallback_uses_cancelled_but_never_failed(self):
        from quodeq.services.scoring_view import select_default_view_runs
        runs = [
            self._run("r3", RunState.FAILED),
            self._run("r2", RunState.CANCELLED),
            self._run("r1", RunState.RUNNING),
        ]
        assert [r.run_id for r in select_default_view_runs(runs)] == ["r2"]

    def test_failed_only_project_gets_nothing(self):
        from quodeq.services.scoring_view import select_default_view_runs
        runs = [self._run("r1", RunState.FAILED)]
        assert select_default_view_runs(runs) == []


class TestSelectTrendRuns:
    """The trend/history-chart run set, centralised next to its siblings.

    Behavior-preserving move of the inline 'not cancelled/failed' filters
    from dashboard.py and scoring/__init__.py: the trend includes
    running entries (History renders their 'running' row from them),
    while the CLIENT keeps them from representing chart buckets
    (dailyGrouping.isBucketEligible).
    """

    @staticmethod
    def _run(run_id, status):
        from quodeq.data.fs.report_parser.runs import RunInfo
        return RunInfo(run_id=run_id, date_iso="2026-01-01", date_label="Jan 01", status=status)

    def test_keeps_done_and_running_drops_cancelled_and_failed(self):
        from quodeq.services.scoring_view import select_trend_runs
        runs = [
            self._run("r4", RunState.RUNNING),
            self._run("r3", RunState.DONE),
            self._run("r2", RunState.CANCELLED),
            self._run("r1", RunState.FAILED),
        ]
        assert [r.run_id for r in select_trend_runs(runs)] == ["r4", "r3"]
