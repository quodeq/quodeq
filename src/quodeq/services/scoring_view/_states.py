"""Run state vocabulary + pure-function predicates.

This module contains *only* predicates over a run's status string and
exit reason — no I/O, no filesystem reads. The companion module
``_resolution.py`` does the I/O-bound work using these predicates.

Why pure: the rules in this file are the project's *contract* with
itself about what each run state means for visibility. Keeping them
side-effect-free means tests can pin them with a single ``assert`` and
no fixtures, and they can be composed into other predicates safely.

See ``README.md`` (next to this file) for the canonical model.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Run state vocabulary
# ---------------------------------------------------------------------------
#
# These string values match what ``data.fs.report_parser.runs.list_runs``
# returns in ``RunInfo.status``. Keeping the source-of-truth definitions
# here (rather than scattered around) means a single ``grep`` finds every
# place that branches on a state — and any new state must declare its
# semantics in this file before it can be visible elsewhere.

RUN_STATE_COMPLETE = "complete"
"""Natural completion: every dim scored, lifecycle reached DONE."""

RUN_STATE_IN_PROGRESS = "in_progress"
"""Currently running. Dims that finish mid-run produce trustworthy evals."""

RUN_STATE_CANCELLED = "cancelled"
"""Stopped before natural completion. ``exit_reason`` distinguishes
budgeted-timeout (success) from signal/stale/error (incomplete)."""

RUN_STATE_FAILED = "failed"
"""System error. Eval files unreliable; never trust."""


# ---------------------------------------------------------------------------
# Successful exit reasons
# ---------------------------------------------------------------------------
#
# A ``cancelled`` run may still be a *successful* run if it stopped
# because of a user-configured budget rather than a failure. The exit
# reasons listed here mark that boundary.
#
# Today this set is empty: the codebase doesn't yet distinguish a budget-
# triggered cancel from any other cancel in ``exit_reason``. When run-
# level timeouts are wired through (separate PR), the new reason string
# joins this set and ``is_successful_run`` immediately picks it up — no
# other code needs to change.

SUCCESSFUL_CANCEL_REASONS: frozenset[str] = frozenset()
"""Exit reasons that mark a ``cancelled`` run as a budgeted success.

Empty for now. Extend when run-level max-duration support lands; e.g.
``frozenset({"max_duration_exceeded"})``. Anything not in this set is
treated as a failure-style cancellation (manual signal, stale-detect,
exception, etc.) — its data is preserved for incremental salvage but
not promoted to overview cards or history rows.
"""


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------

def is_successful_run(status: str, exit_reason: str | None = None) -> bool:
    """A run that reached a natural end with trustworthy data.

    Used by:
      - ``HistoryPage``'s row visibility filter (only successful runs show).
      - The score-history chart's per-day bucket aggregation (each bar
        reflects the day's latest *successful* run).
      - The overview's default-run selection upstream of bucket choice.

    A run is successful when **either**:

      1. ``status == "complete"`` — natural completion, all dims scored.
      2. ``status == "cancelled"`` AND ``exit_reason`` is in
         ``SUCCESSFUL_CANCEL_REASONS`` — a budgeted timeout, which is
         the user's *intent* (e.g. "stop at 10 minutes"). The data
         within the budget is real, the model didn't error.

    Anything else (manual signal cancel, stale-detect, exception, error,
    or in-progress runs) is **not** successful for the purposes of this
    predicate.
    """
    if status == RUN_STATE_COMPLETE:
        return True
    if status == RUN_STATE_CANCELLED and exit_reason in SUCCESSFUL_CANCEL_REASONS:
        return True
    return False


def is_trustable_run(status: str) -> bool:
    """A run whose eval files may carry real, usable per-dim data.

    Broader than ``is_successful_run``: includes ``cancelled`` and
    ``in_progress`` because both can have dims that finished cleanly
    before the umbrella run stopped (or is still running). Their data
    is real; just not promoted to the overview cards by default.

    Used by:
      - ``find_previous_fingerprint`` — incremental classification can
        reuse cancelled-run analyzed files for next-run salvage.
      - ``is_visible_in_history`` (composed predicate) for the broader
        existence check before the per-eval-file trustworthiness scan.

    Excludes ``failed`` only — system errors leave the run in an
    indeterminate state where any partial scoring is suspect.
    """
    return status in (RUN_STATE_COMPLETE, RUN_STATE_IN_PROGRESS, RUN_STATE_CANCELLED)


def is_eligible_for_default_view(status: str) -> bool:
    """A run whose data can drive the overview cards / headline by default.

    The strictest of the three predicates: only ``complete`` qualifies.

      - ``in_progress`` is excluded because the umbrella run hasn't
        terminated. Already-scored dims are real, but counting them in
        the overview while the run is alive means the cards twitch each
        time a dim finishes; users instead want a stable view of the
        *last finished* run until the new one terminates. Mid-flight
        dims are still inspectable on the run-detail page (clicking the
        running row in history).
      - ``cancelled`` is excluded because a signal-cancelled run can
        have sparse-coverage stub evals (model only got through 5% of
        files before stop) — silently mixing those into the cards
        distorts the score.
      - ``failed`` is excluded — the run errored before producing
        trustworthy data.

    A user can still explicitly navigate to a non-complete run via the
    chart or history table; this predicate only governs the *default*
    landing-page selection, where surprises are unwelcome.

    Used by:
      - ``accumulated._compute_result`` — filtering the per-dim "latest"
        pick across runs.
      - ``dashboard._resolve_selected_run("latest")`` — picking the
        default run when the user lands without an explicit selection.

    Both call sites consult this single predicate so they cannot drift
    apart (a class of bug we hit repeatedly before centralisation).
    """
    return status == RUN_STATE_COMPLETE


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------
# Listed explicitly so ``from ._states import *`` on the package
# ``__init__`` only pulls intentional symbols, not constants meant to be
# private to this module.

__all__ = [
    "RUN_STATE_COMPLETE",
    "RUN_STATE_IN_PROGRESS",
    "RUN_STATE_CANCELLED",
    "RUN_STATE_FAILED",
    "SUCCESSFUL_CANCEL_REASONS",
    "is_successful_run",
    "is_trustable_run",
    "is_eligible_for_default_view",
]
