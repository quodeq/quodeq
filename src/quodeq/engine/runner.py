"""Re-export for backward compatibility — moved to quodeq.analysis.runner."""
from quodeq.analysis.runner import (  # noqa: F401
    AnalysisOptions,
    RunConfig,
    EvaluationError,
    run,
    run_per_dimension,
    _PluginContext,
    _build_dimension_prompt,
    _run_dimension_analysis,
    _parse_dimension_evidence,
    _process_dimension_with_subagents,
    _load_plugin_context,
    _log_dimension_result,
    _process_single_dimension,
    _run_dimensions,
)
from quodeq.engine._runner_markers import CC_MARKER_KEY, cleanup_stream  # noqa: F401
