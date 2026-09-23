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
# Pure predicates — no I/O, safe to call from anywhere
# ---------------------------------------------------------------------------
from ._states import (
    TREND_STATES,
    is_eligible_for_default_view,
    select_default_view_runs,
    select_trend_runs,
)

# ---------------------------------------------------------------------------
# Models — frozen carriers returned by the resolvers
# ---------------------------------------------------------------------------
from ._models import (
    DimResolution,
    BucketView,
    RunSummary,
)


__all__ = [
    # Vocabulary
    "TREND_STATES",
    # Predicates
    "is_eligible_for_default_view",
    "select_default_view_runs",
    "select_trend_runs",
    # Models
    "DimResolution",
    "BucketView",
    "RunSummary",
]
