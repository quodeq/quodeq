"""scoring_view — single source of truth for which run/dim data each view shows.

See ``README.md`` next to this file for the canonical model. Every
public symbol here is a contract: callers depend on these names and
behaviors, not on the internal structure of ``_states`` / ``_models``
/ ``_resolution`` / ``_buckets``.

Internal modules carry leading underscores precisely because they're
not the boundary. Reach **through** this ``__init__`` from anywhere
outside the package.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Run state vocabulary — constants callers can pattern-match against
# ---------------------------------------------------------------------------
from ._states import (
    RUN_STATE_COMPLETE,
    RUN_STATE_IN_PROGRESS,
    RUN_STATE_CANCELLED,
    RUN_STATE_FAILED,
    SUCCESSFUL_CANCEL_REASONS,
)

# ---------------------------------------------------------------------------
# Pure predicates — no I/O, safe to call from anywhere
# ---------------------------------------------------------------------------
from ._states import (
    is_successful_run,
    is_trustable_run,
    is_eligible_for_default_view,
)

# ---------------------------------------------------------------------------
# Models — frozen carriers returned by the resolvers
# ---------------------------------------------------------------------------
from ._models import (
    DimResolution,
    BucketView,
    RunSummary,
)

# ---------------------------------------------------------------------------
# I/O-bound resolvers — read eval files, return models
# ---------------------------------------------------------------------------
from ._resolution import (
    resolve_latest_per_dim,
    is_visible_in_history,
    is_eligible_for_chart_bar,
)

# ---------------------------------------------------------------------------
# Bucketing — group runs for the score-history chart
# ---------------------------------------------------------------------------
from ._buckets import (
    bucket_runs_by_day,
    pick_representative_run,
)


__all__ = [
    # Vocabulary
    "RUN_STATE_COMPLETE",
    "RUN_STATE_IN_PROGRESS",
    "RUN_STATE_CANCELLED",
    "RUN_STATE_FAILED",
    "SUCCESSFUL_CANCEL_REASONS",
    # Predicates
    "is_successful_run",
    "is_trustable_run",
    "is_eligible_for_default_view",
    # Models
    "DimResolution",
    "BucketView",
    "RunSummary",
    # Resolvers
    "resolve_latest_per_dim",
    "is_visible_in_history",
    "is_eligible_for_chart_bar",
    # Bucketing
    "bucket_runs_by_day",
    "pick_representative_run",
]
