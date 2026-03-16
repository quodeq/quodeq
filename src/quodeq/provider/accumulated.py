"""Re-export for backward compatibility — moved to quodeq.services.accumulated."""
from quodeq.services.accumulated import (  # noqa: F401
    AccumulatedCacheConfig,
    compute_accumulated,
    numeric_average,
    _aggregate_severity_counts,
    _compute_accumulated_scores,
    _compute_accumulated_trends,
    _read_all_run_data,
    _AccumulatedResult,
)
