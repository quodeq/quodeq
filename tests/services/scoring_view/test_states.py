"""Tests for the pure state predicates.

Pinning the contracts described in scoring_view/README.md so that:

  - ``is_successful_run`` matches only the user-intended success cases.
  - ``is_trustable_run`` includes cancelled (so incremental can salvage
    partial work) and in_progress (so already-scored dims are real for
    next-run salvage) but excludes failed.
  - ``is_eligible_for_default_view`` is the strictest rule: only
    ``complete`` runs drive the overview cards. in_progress and
    cancelled are both excluded — overview waits for the umbrella run
    to terminate before counting any of its dims.

A mismatch between any two of these predicates is what the package
exists to prevent — these tests fail fast if the rules drift.
"""
from __future__ import annotations

from quodeq.services.scoring_view import (
    SUCCESSFUL_CANCEL_REASONS,
    is_eligible_for_default_view,
    is_successful_run,
    is_trustable_run,
)


# ---------------------------------------------------------------------------
# is_successful_run
# ---------------------------------------------------------------------------

class TestIsSuccessfulRun:
    def test_complete_is_successful(self):
        # The unambiguous case: run reached its natural end, every dim
        # scored, lifecycle transitioned to DONE.
        assert is_successful_run("complete") is True

    def test_in_progress_is_not_successful(self):
        # A still-running scan hasn't proven success yet. We have a
        # separate predicate (``is_eligible_for_default_view``) for the
        # "show this in the overview while it's running" allowance.
        assert is_successful_run("in_progress") is False

    def test_failed_is_not_successful(self):
        assert is_successful_run("failed") is False

    def test_cancelled_default_is_not_successful(self):
        # Without an exit_reason, a cancellation is treated as failure-
        # mode (signal cancel, stale-detect, exception). The user's
        # data is still on disk for incremental salvage but doesn't
        # appear as a successful run.
        assert is_successful_run("cancelled") is False
        assert is_successful_run("cancelled", exit_reason=None) is False

    def test_cancelled_with_signal_reason_is_not_successful(self):
        assert is_successful_run("cancelled", exit_reason="signal_SIGTERM") is False
        assert is_successful_run("cancelled", exit_reason="stale_detected") is False

    def test_cancelled_with_budget_reason_extension_point(self):
        # When a budgeted-timeout reason joins SUCCESSFUL_CANCEL_REASONS,
        # is_successful_run picks it up automatically. Today the set is
        # empty; this test pins the extension contract so adding a
        # reason later is one-line + automatic.
        if SUCCESSFUL_CANCEL_REASONS:
            sample_reason = next(iter(SUCCESSFUL_CANCEL_REASONS))
            assert is_successful_run("cancelled", exit_reason=sample_reason) is True


# ---------------------------------------------------------------------------
# is_trustable_run
# ---------------------------------------------------------------------------

class TestIsTrustableRun:
    def test_complete_is_trustable(self):
        assert is_trustable_run("complete") is True

    def test_in_progress_is_trustable(self):
        # A running scan with at least one dim scored is real data —
        # incremental classification can use it as ``analyzed_files``.
        assert is_trustable_run("in_progress") is True

    def test_cancelled_is_trustable(self):
        # The wider rule than ``is_eligible_for_default_view``: a
        # cancelled run's eval files are real and feed the next run's
        # incremental classification, even if they don't drive the
        # current-run overview cards.
        assert is_trustable_run("cancelled") is True

    def test_failed_is_not_trustable(self):
        # Failures imply system errors before / during scoring; nothing
        # the run wrote is trustworthy.
        assert is_trustable_run("failed") is False


# ---------------------------------------------------------------------------
# is_eligible_for_default_view
# ---------------------------------------------------------------------------

class TestIsEligibleForDefaultView:
    def test_complete_is_eligible(self):
        assert is_eligible_for_default_view("complete") is True

    def test_in_progress_is_NOT_eligible(self):
        # An in-progress run's already-scored dims are real but the
        # umbrella run hasn't terminated, so they don't count toward
        # the overview yet. Users see those dims on the run-detail
        # page (clicking the running row in history); the overview
        # cards only update when the run reaches a terminal state.
        assert is_eligible_for_default_view("in_progress") is False

    def test_cancelled_is_NOT_eligible(self):
        # A signal-cancelled run can have stub or sparse-coverage
        # evals; promoting them to the cards distorts the score the
        # user reads. Excluded from the default view; user can still
        # navigate explicitly.
        assert is_eligible_for_default_view("cancelled") is False

    def test_failed_is_NOT_eligible(self):
        assert is_eligible_for_default_view("failed") is False


# ---------------------------------------------------------------------------
# Cross-predicate consistency invariants
# ---------------------------------------------------------------------------

class TestPredicateConsistency:
    """Cross-predicate invariants that the README claims hold."""

    def test_eligible_for_default_view_implies_trustable(self):
        # The narrower rule must be a strict subset of the broader
        # rule. If any state passes ``eligible_for_default_view`` but
        # not ``trustable``, the cards would silently display data
        # we elsewhere consider untrustworthy — a contract violation.
        for status in ("complete", "in_progress", "cancelled", "failed"):
            if is_eligible_for_default_view(status):
                assert is_trustable_run(status), (
                    f"{status} is eligible-for-default-view but NOT trustable. "
                    "The README invariant says the default view is a strict "
                    "subset of the trustable set."
                )

    def test_successful_implies_trustable(self):
        # A successful run is by definition one whose data we trust.
        # The set of successful states must be a subset of trustable.
        # ``is_successful_run`` requires status + reason; iterate
        # representative pairs.
        successful_pairs = [("complete", None), ("complete", "anything")]
        for reason in SUCCESSFUL_CANCEL_REASONS:
            successful_pairs.append(("cancelled", reason))
        for status, reason in successful_pairs:
            if is_successful_run(status, reason):
                assert is_trustable_run(status), (
                    f"{status}/{reason} is successful but NOT trustable."
                )


class TestSelectDefaultViewRuns:
    """One shared rule for which runs feed the accumulated/default view.

    The Overview (accumulated._compute_result) and the repositories-screen
    project card must consult the same selection or their grades diverge:
    the card used to take the newest run of ANY status while the Overview
    took complete-only. And the fallback used to include failed runs,
    letting a partial failed run masquerade as a normal project grade.
    """

    @staticmethod
    def _run(run_id, status):
        from quodeq.services.ports import RunInfo
        return RunInfo(run_id=run_id, date_iso="2026-01-01", date_label="Jan 01", status=status)

    def test_complete_runs_win(self):
        from quodeq.services.scoring_view import select_default_view_runs
        runs = [
            self._run("r3", "cancelled"),
            self._run("r2", "complete"),
            self._run("r1", "failed"),
        ]
        assert [r.run_id for r in select_default_view_runs(runs)] == ["r2"]

    def test_fallback_uses_cancelled_but_never_failed(self):
        from quodeq.services.scoring_view import select_default_view_runs
        runs = [
            self._run("r3", "failed"),
            self._run("r2", "cancelled"),
            self._run("r1", "in_progress"),
        ]
        assert [r.run_id for r in select_default_view_runs(runs)] == ["r2"]

    def test_failed_only_project_gets_nothing(self):
        from quodeq.services.scoring_view import select_default_view_runs
        runs = [self._run("r1", "failed")]
        assert select_default_view_runs(runs) == []
