"""Dimension loop orchestrators — run dimensions sequentially or incrementally."""
from __future__ import annotations

import json
from copy import copy
from collections.abc import Callable

from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.core.evidence.model import Evidence
# NOTE: logging in inner layer — tracked for middleware extraction
from quodeq.shared.logging import log_info, log_warning


def check_zero_findings(
    result: dict[str, Evidence], source_file_count: int, skipped_count: int = 0,
) -> None:
    """Raise EvaluationError if all dimensions produced zero findings."""
    from quodeq.analysis.runner import EvaluationError

    if not result or source_file_count <= 0:
        return
    total_findings = sum(
        sum(len(pe.violations) + len(pe.compliance) for pe in ev.principles.values())
        for ev in result.values()
    )
    if total_findings == 0:
        skip_msg = f" ({skipped_count} skipped)" if skipped_count else ""
        raise EvaluationError(
            f"Evaluation produced 0 findings across {len(result)} dimensions{skip_msg}. "
            f"This usually means the AI CLI could not read files or report findings "
            f"\u2014 check tool permissions and MCP configuration."
        )


def run_incremental_loop(
    config: RunConfig, dimensions: list[str], ctx: _AnalysisContext,
    *, process_fn: Callable[..., Evidence | None] | None = None,
) -> dict[str, Evidence]:
    """Run incremental per-dimension analysis."""
    from quodeq.analysis._incremental import run_dimension_incremental
    from quodeq.analysis.runner import _process_single_dimension, _log_dimension_result
    from quodeq.engine._runner_markers import emit_marker

    _process = process_fn or _process_single_dimension
    result: dict[str, Evidence] = {}
    for idx, dimension in enumerate(dimensions, 1):
        emit_marker("analyzing", dimension=dimension)
        log_info(f"\u2192 [{idx}/{ctx.total}] Analyzing {dimension} (incremental)")
        try:
            ev = run_dimension_incremental(config, dimension, idx, ctx)
        except (OSError, KeyError, ValueError, RuntimeError) as exc:
            log_warning(f"[{idx}/{ctx.total}] {dimension} \u2014 incremental failed: {exc}, falling back to full")
            original_options = config.options
            config.options = copy(original_options)
            config.options.incremental_file_filter = None
            try:
                ev = _process(config, dimension, idx, ctx)
            finally:
                config.options = original_options
        if ev:
            _log_dimension_result(ev, dimension, idx, ctx.total)
            result[dimension] = ev
    check_zero_findings(result, config.source_file_count)
    return result


def run_per_dimension_loop(
    config: RunConfig, dimensions: list[str], ctx: _AnalysisContext,
    *, process_fn: Callable[..., Evidence | None] | None = None,
) -> dict[str, Evidence]:
    """Per-dimension loop (fallback or single-dimension)."""
    from quodeq.analysis.runner import _process_single_dimension

    _process = process_fn or _process_single_dimension
    result: dict[str, Evidence] = {}
    skipped_count = 0
    for idx, dimension in enumerate(dimensions, 1):
        try:
            ev = _process(config, dimension, idx, ctx)
        except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
            log_warning(f"[{idx}/{ctx.total}] {dimension} \u2014 failed: {exc}")
            skipped_count += 1
            continue
        if ev is None:
            skipped_count += 1
            continue
        result[dimension] = ev
    check_zero_findings(result, config.source_file_count, skipped_count)
    return result
