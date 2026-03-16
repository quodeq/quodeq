"""Re-export for backward compatibility — moved to quodeq.analysis.runner."""
from quodeq.analysis.runner import (  # noqa: F401
    AnalysisOptions,
    RunConfig,
    EvaluationError,
    run,
    run_per_dimension,
)
from quodeq.engine._runner_markers import CC_MARKER_KEY, cleanup_stream  # noqa: F401
