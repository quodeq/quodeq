"""Back-compat shim — re-exports the public API of ``scoring_view``.

The original module that introduced ``DimResolution`` and the
``resolve_*`` / ``is_*`` helpers (#311). Its content has moved into the
``scoring_view`` package, where it lives alongside the canonical model
documentation (see ``scoring_view/README.md``).

This file remains so existing imports continue to resolve while call
sites are migrated PR-by-PR. Once every caller has been updated to
import from ``quodeq.services.scoring_view`` directly, this shim
disappears in a final cleanup PR.

**For new code: import from ``quodeq.services.scoring_view`` directly.**
"""
from __future__ import annotations

# Re-export every previously-public symbol so the old import path still
# works. New code should import from ``scoring_view`` directly; this
# shim only exists for the migration window.
from quodeq.services.scoring_view import (
    DimResolution,
    SUCCESSFUL_CANCEL_REASONS,
    bucket_runs_by_day,
    is_eligible_for_chart_bar,
    is_eligible_for_default_view,
    is_successful_run,
    is_trustable_run,
    is_visible_in_history,
    pick_representative_run,
    resolve_latest_per_dim,
)

# Internal constants that some pre-package code (and tests) reached
# into directly. We re-expose them but they're not part of the public
# contract — prefer the named predicates that consume them.
from quodeq.services.scoring_view._resolution import (  # noqa: F401
    _is_trustworthy_eval as _is_trustworthy,
    _load_eval,
    _trustworthy_dims_in_run as _trustworthy_eval_dims,
)


# Pre-existing symbol used by ``_incr_change_detection``: this used to
# be a private constant of this module. Now lives in ``scoring_view``,
# but the imports from incr-change still work because they reach into
# ``_states`` directly (or, equivalently, through this shim).
_TRUSTABLE_RUN_STATES = frozenset({"complete", "in_progress", "cancelled"})


__all__ = [
    "DimResolution",
    "SUCCESSFUL_CANCEL_REASONS",
    "bucket_runs_by_day",
    "is_eligible_for_chart_bar",
    "is_eligible_for_default_view",
    "is_successful_run",
    "is_trustable_run",
    "is_visible_in_history",
    "pick_representative_run",
    "resolve_latest_per_dim",
]
