"""Pipeline coordination — dimension orchestration, merging, and public API."""
from __future__ import annotations

from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis._dimension_ops import (
    _build_dimension_prompt,
    _log_dimension_result,
    _parse_dimension_evidence,
    _process_single_dimension,
    _run_dimension_analysis,
    _save_dimension_fingerprint,
)
from quodeq.core.evidence.model import Evidence
from quodeq.core.evidence.merge import merge_evidence
from quodeq.engine._runner_markers import emit_marker
from quodeq.shared.logging import log_warning


class EvaluationError(RuntimeError):
    """Raised when an evaluation completes but produces no usable findings."""


def load_analysis_context(config: RunConfig) -> tuple[list[str], _AnalysisContext]:
    """Load dimensions data and resolve which dimensions to analyze."""
    from quodeq.analysis._incremental import load_analysis_context as _load_ctx
    return _load_ctx(config)


def _run_dimensions(config: RunConfig) -> dict[str, Evidence]:
    """Run AI analysis for each dimension and return per-dimension Evidence."""
    from quodeq.analysis._incremental import (
        run_incremental_loop, run_per_dimension_loop,
    )

    dimensions, ctx = load_analysis_context(config)

    if config.options.incremental:
        emit_marker("setup", dimensions=dimensions)
        return run_incremental_loop(
            config, dimensions, ctx,
            process_fn=_process_single_dimension,
            log_result_fn=_log_dimension_result,
        )

    emit_marker("setup", dimensions=dimensions)

    # Consolidated mode: evaluate all dimensions in one pass
    if (config.options.consolidated
            and len(dimensions) > 1
            and config.options.max_subagents > 1):
        from quodeq.analysis.subagents.runner import process_consolidated_dimensions
        try:
            result = process_consolidated_dimensions(config, dimensions, ctx)
            if result:
                for dim, ev in result.items():
                    idx = dimensions.index(dim) + 1 if dim in dimensions else 0
                    _log_dimension_result(ev, dim, idx, len(dimensions))
                return result
            log_warning("Consolidated mode produced no results, falling back to per-dimension")
        except (OSError, KeyError, ValueError, RuntimeError) as exc:
            log_warning(f"Consolidated mode failed: {exc}, falling back to per-dimension")

    return run_per_dimension_loop(
        config, dimensions, ctx,
        process_fn=_process_single_dimension,
    )


def run(config: RunConfig) -> Evidence:
    """Orchestrate: load dimensions -> per-dimension AI analysis -> merged Evidence."""
    return merge_evidence(
        list(_run_dimensions(config).values()),
        source_file_count=config.source_file_count,
        src=str(config.src),
        language=config.language,
    )


def run_per_dimension(config: RunConfig) -> dict[str, Evidence]:
    """Like run(), but returns a dict of {dimension_id: Evidence} without merging."""
    return _run_dimensions(config)
