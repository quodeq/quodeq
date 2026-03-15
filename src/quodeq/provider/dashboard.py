"""Re-export for backward compatibility — moved to quodeq.services.dashboard."""
from quodeq.services.dashboard import *  # noqa: F401,F403
from quodeq.services.dashboard import (  # noqa: F401 — underscore names skipped by *
    _collect_previous_scores,
    _collect_stale_dimensions,
    _enrich_dimensions_with_trend,
    _build_accumulated_trend,
    _build_dashboard_result,
    _compute_dashboard_payload,
    _make_run_dimension_fetcher,
    _resolve_selected_run,
    _DashboardPayload,
    _SelectedRunContext,
)
