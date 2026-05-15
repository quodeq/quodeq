"""Dimension orchestration: delegates to DimensionRunner.

Thin shim retained for backward-compatible imports from _pipeline.py and tests.
The canonical implementation lives in ``analysis.dimension_runner``.
"""
from __future__ import annotations

from quodeq.analysis._dimension_steps import (  # noqa: F401 — re-export for _pipeline.py
    _build_dimension_prompt,
    _parse_dimension_evidence,
    _run_dimension_analysis,
)
from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis.dimension_runner import DimensionRunner, _log_dimension_result  # noqa: F401
from quodeq.core.evidence.model import Evidence

_runner = DimensionRunner()


def _process_single_dimension(
    config: RunConfig, dimension: str, idx: int, ctx: _AnalysisContext,
    *, emit_log: bool = True,
) -> Evidence | None:
    return _runner.run(config, dimension, idx, ctx, emit_log=emit_log)


def _run_dimension_incremental(
    config: RunConfig, dimension: str, idx: int, ctx: _AnalysisContext,
) -> Evidence | None:
    return _runner.run(config, dimension, idx, ctx, emit_log=False)
