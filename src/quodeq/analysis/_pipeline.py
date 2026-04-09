"""Pipeline coordination — dimension orchestration, merging, and public API."""
from __future__ import annotations

from collections.abc import Callable

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


from quodeq.analysis.errors import EvaluationError as EvaluationError  # re-export


def load_analysis_context(config: RunConfig) -> tuple[list[str], _AnalysisContext]:
    """Load dimensions data and resolve which dimensions to analyze."""
    from quodeq.analysis._incremental import load_analysis_context as _load_ctx
    return _load_ctx(config)


def _run_dimensions(
    config: RunConfig,
    on_dimension_done: "Callable[[str, Evidence], None] | None" = None,
) -> dict[str, Evidence]:
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
            on_dimension_done=on_dimension_done,
        )

    emit_marker("setup", dimensions=dimensions)

    # Consolidated mode: evaluate all dimensions in one pass.
    # Disabled for API providers — per-dimension gives better coverage
    # since local models struggle with 8 dimensions in one prompt.
    from quodeq.analysis.subprocess import _get_provider_type
    from quodeq.shared.utils import get_ai_cmd
    _provider_type = _get_provider_type(get_ai_cmd())
    if (config.options.consolidated
            and len(dimensions) > 1
            and config.options.max_subagents > 1
            and _provider_type != "api"):
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
        on_dimension_done=on_dimension_done,
    )


def run(config: RunConfig) -> Evidence:
    """Orchestrate: load dimensions -> per-dimension AI analysis -> merged Evidence."""
    return merge_evidence(
        list(_run_dimensions(config).values()),
        source_file_count=config.source_file_count,
        src=str(config.src),
        language=config.language,
    )


def run_per_dimension(
    config: RunConfig,
    on_dimension_done: "Callable[[str, Evidence], None] | None" = None,
) -> dict[str, Evidence]:
    """Like run(), but returns a dict of {dimension_id: Evidence} without merging."""
    return _run_dimensions(config, on_dimension_done=on_dimension_done)
