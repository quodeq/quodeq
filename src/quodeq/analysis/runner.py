"""Runner — public façade for the analysis pipeline.

Implementation modules:
  _dimension_steps.py  — prompt building, AI execution, evidence parsing
  dimension_runner.py  — single-dimension orchestration (DimensionRunner)
  _pipeline.py         — cross-dimension orchestration and merging
"""
from __future__ import annotations

from quodeq.analysis._dimensions import load_universal_dimensions as load_universal_dimensions
from quodeq.analysis._types import (
    AnalysisOptions as AnalysisOptions,
    RunConfig as RunConfig,
)
from quodeq.analysis._pipeline import (
    EvaluationError as EvaluationError,
    load_analysis_context as load_analysis_context,
    run as run,
    run_per_dimension as run_per_dimension,
)
