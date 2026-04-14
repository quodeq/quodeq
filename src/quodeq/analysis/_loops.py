"""Dimension loop orchestrators — run dimensions sequentially or incrementally."""
from __future__ import annotations

import json
from copy import copy
from dataclasses import replace
from collections.abc import Callable

from quodeq.analysis._incremental_orchestrator import run_dimension_incremental
from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis.errors import EvaluationError
from quodeq.core.evidence.model import Evidence
from quodeq.engine._runner_markers import emit_marker
# NOTE: logging in inner layer — tracked for middleware extraction
from quodeq.shared.logging import log_info, log_warning


def check_zero_findings(
    result: dict[str, Evidence], source_file_count: int, skipped_count: int = 0,
) -> None:
    """Raise EvaluationError if all dimensions produced zero findings."""
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
    *, process_fn: Callable[..., Evidence | None],
    log_result_fn: Callable[..., None],
    on_dimension_done: Callable[[str, Evidence], None] | None = None,
) -> dict[str, Evidence]:
    """Run incremental per-dimension analysis.

    Args:
        config: Run configuration for this evaluation.
        dimensions: Dimension identifiers to analyze.
        ctx: Shared analysis context (total count, etc.).
        process_fn: Callback to process a single dimension (signature:
            ``(config, dimension, idx, ctx) -> Evidence | None``).
        log_result_fn: Callback to log a completed dimension result.
    """
    result: dict[str, Evidence] = {}
    for idx, dimension in enumerate(dimensions, 1):
        emit_marker("analyzing", dimension=dimension)
        log_info(f"\u2192 [{idx}/{ctx.total}] Analyzing {dimension} (incremental)")
        try:
            ev = run_dimension_incremental(config, dimension, idx, ctx)
        except (OSError, KeyError, ValueError, RuntimeError) as exc:
            log_warning(f"[{idx}/{ctx.total}] {dimension} \u2014 incremental failed: {exc}, falling back to full")
            fallback_options = copy(config.options)
            fallback_options.incremental_file_filter = None
            fallback_config = replace(config, options=fallback_options)
            ev = process_fn(fallback_config, dimension, idx, ctx)
        if ev:
            log_result_fn(ev, dimension, idx, ctx.total)
            result[dimension] = ev
            if on_dimension_done:
                on_dimension_done(dimension, ev)
    check_zero_findings(result, config.source_file_count)
    return result


def run_per_dimension_loop(
    config: RunConfig, dimensions: list[str], ctx: _AnalysisContext,
    *, process_fn: Callable[..., Evidence | None],
    on_dimension_done: Callable[[str, Evidence], None] | None = None,
) -> dict[str, Evidence]:
    """Per-dimension loop (fallback or single-dimension).

    Args:
        config: Run configuration for this evaluation.
        dimensions: Dimension identifiers to analyze.
        ctx: Shared analysis context (total count, etc.).
        process_fn: Callback to process a single dimension (signature:
            ``(config, dimension, idx, ctx) -> Evidence | None``).
    """
    result: dict[str, Evidence] = {}
    skipped_count = 0
    for idx, dimension in enumerate(dimensions, 1):
        try:
            ev = process_fn(config, dimension, idx, ctx)
        except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
            log_warning(f"[{idx}/{ctx.total}] {dimension} \u2014 failed: {exc}")
            skipped_count += 1
            continue
        if ev is None:
            skipped_count += 1
            continue
        result[dimension] = ev
        if on_dimension_done:
            on_dimension_done(dimension, ev)
    check_zero_findings(result, config.source_file_count, skipped_count)
    return result
