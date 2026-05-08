"""Runner — public façade (re-exports for backward compatibility).

Implementation split into:
  _dimension_ops.py  — prompt building, AI execution, evidence parsing
  _pipeline.py       — dimension orchestration and merging
"""
from __future__ import annotations

# Re-export types that external callers import from here
from quodeq.analysis._dimensions import (
    DimensionEntry as DimensionEntry,
    DimensionsConfig as DimensionsConfig,
    load_universal_dimensions as load_universal_dimensions,
)
from quodeq.analysis._types import (  # noqa: F401 — re-export
    AnalysisOptions as AnalysisOptions,
    RunConfig as RunConfig,
    _AnalysisContext as _AnalysisContext,
)
from quodeq.analysis.manifest import AnalysisTarget, SourceManifest  # noqa: F401
from quodeq.analysis.subprocess import AnalysisConfig, HeartbeatCallback, count_files_from_stream, run_analysis  # noqa: F401,E501
from quodeq.engine._runner_markers import CC_MARKER_KEY, cleanup_stream  # noqa: F401
from quodeq.shared.validation import validate_path_segment  # noqa: F401

# Re-export dimension step functions (used by tests that patch these)
from quodeq.analysis._dimension_steps import (
    _build_dimension_prompt as _build_dimension_prompt,
    _parse_dimension_evidence as _parse_dimension_evidence,
    _run_dimension_analysis as _run_dimension_analysis,
    _try_parse_stream_evidence as _try_parse_stream_evidence,
)

# Re-export dimension orchestration (used by _loops.py, _incremental.py, _backfill.py)
from quodeq.analysis._dimension_ops import (
    _log_dimension_result as _log_dimension_result,
    _process_single_dimension as _process_single_dimension,
    _run_dimension_incremental as _run_dimension_incremental,
)

# Re-export pipeline API (used by cli.py, scoring_pipeline.py, tests)
from quodeq.analysis._pipeline import (
    EvaluationError as EvaluationError,
    load_analysis_context as load_analysis_context,
    run as run,
    run_per_dimension as run_per_dimension,
)
