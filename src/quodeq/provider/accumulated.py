"""Re-export for backward compatibility — moved to quodeq.services.accumulated."""
from quodeq.services.accumulated import *  # noqa: F401,F403
from quodeq.services.accumulated import (  # noqa: F401 — underscore names skipped by *
    _aggregate_severity_counts,
    _compute_accumulated_scores,
    _compute_accumulated_trends,
    _read_all_run_data,
    _AccumulatedResult,
)
