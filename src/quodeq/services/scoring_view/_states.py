"""Which runs the scoring views may show (pure predicates over RunState)."""
from __future__ import annotations

from collections.abc import Iterable, Sequence

from quodeq.core.run.state import RunState

# States a trend line may plot: finished runs and the one still running.
TREND_STATES: frozenset[RunState] = frozenset({RunState.DONE, RunState.RUNNING})


def is_eligible_for_default_view(status: RunState) -> bool:
    """Only a finished run may be the project's headline run."""
    return status is RunState.DONE


def select_default_view_runs(run_infos: Sequence) -> list:
    """The single run-set selection for the accumulated/default view.

    ``DONE`` runs when any exist. Otherwise fall back to ``CANCELLED``
    runs (a keep-findings cancel is real data the user chose to keep, and
    a fresh project whose every attempt was stopped early should still
    show what it has). ``RUNNING`` never feeds the default view (the
    umbrella run hasn't terminated) and ``FAILED`` never does either (the
    run errored; partial scoring is suspect) — including in the fallback,
    so a partial failed run cannot masquerade as the project grade.

    Used by:
      - ``accumulated._compute_result`` — the Overview cards/headline.
      - ``_fs_metadata._read_accumulated_summary`` — the repositories
        screen's project-card grade.

    Both consult this single function so the card a user sees on the
    project list always matches the Overview behind the click.

    Args/returns are ``RunInfo``-shaped objects (anything with a
    ``status`` attribute); order is preserved.
    """
    eligible = [r for r in run_infos if is_eligible_for_default_view(r.status)]
    if eligible:
        return eligible
    return [r for r in run_infos if r.status is RunState.CANCELLED]


def select_trend_runs(run_infos: Iterable) -> list:
    """The run set behind ``dashboard.trend`` / the score-history data.

    ``DONE`` and ``RUNNING`` runs; ``CANCELLED`` and ``FAILED`` are
    dropped — their partial scores are misleading as history points.
    They remain in ``availableRuns`` so the UI can surface them when the
    user asks explicitly.

    ``RUNNING`` entries stay in the trend because the History table
    renders its "running" row from them; the CLIENT keeps them from
    representing chart buckets or the day-highlight union
    (``dailyGrouping.isBucketEligible``), mirroring the default view's
    wait-until-terminal rule.

    Used by:
      - ``_dashboard_history._compute_dashboard_payload`` — history window.
      - ``scoring.get_project_scores`` — the /scores trend.

    Args/returns are ``RunInfo``-shaped objects; order is preserved.
    """
    return [r for r in run_infos if r.status in TREND_STATES]


__all__ = [
    "TREND_STATES",
    "is_eligible_for_default_view",
    "select_default_view_runs",
    "select_trend_runs",
]
