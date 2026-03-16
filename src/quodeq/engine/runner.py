"""Re-export for backward compatibility — moved to quodeq.analysis.runner."""
from quodeq.analysis.runner import *  # noqa: F401,F403
from quodeq.analysis.runner import (  # noqa: F401
    AnalysisOptions,
    EvaluationError,
    RunConfig,
    _PluginContext,
    _build_dimension_prompt,
    _load_plugin_context,
    _log_dimension_result,
    _parse_dimension_evidence,
    _process_dimension_with_subagents,
    _process_single_dimension,
    _run_dimension_analysis,
    _run_dimensions,
    run,
    run_per_dimension,
)
from quodeq.engine._runner_markers import CC_MARKER_KEY, cleanup_stream  # noqa: F401
