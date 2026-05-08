"""Dimension orchestration: single-dimension processing, logging, fingerprinting."""
from __future__ import annotations

from quodeq.analysis._incremental_evidence import save_dimension_fingerprint
from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis._dimension_steps import (
    _build_dimension_prompt,
    _parse_dimension_evidence,
    _run_dimension_analysis,
)
from quodeq.analysis.cache.flags import is_cache_v2_enabled
from quodeq.analysis.subagents.runner import DimensionCallbacks, process_dimension_with_subagents
from quodeq.core.evidence.model import Evidence
from quodeq.engine._runner_markers import emit_marker
from quodeq.shared.logging import log_info, log_success, log_warning


def _save_dimension_fingerprint(
    config: RunConfig, dimension: str, files: list[str] | None = None,
    analyzed_files: set[str] | None = None,
) -> None:
    """Save a fingerprint after any successful dimension analysis."""
    save_dimension_fingerprint(config, dimension, files, analyzed_files)


def _log_dimension_result(ev: Evidence, dimension: str, idx: int, total: int) -> None:
    """Emit scoring marker and log summary for a completed dimension."""
    emit_marker("scoring", dimension=dimension)
    violations = sum(len(pe.violations) for pe in ev.principles.values())
    compliances = sum(len(pe.compliance) for pe in ev.principles.values())
    log_success(f"[{idx}/{total}] {dimension} — {ev.files_read} files, {violations}v/{compliances}c")


def _process_single_dimension(
    config: RunConfig, dimension: str, idx: int, ctx: _AnalysisContext,
    *, emit_log: bool = True,
) -> Evidence | None:
    """Analyze a single dimension: build prompt, run AI, parse evidence."""
    if emit_log:
        emit_marker("analyzing", dimension=dimension)
        log_info(f"→ [{idx}/{ctx.total}] Analyzing {dimension}")

    callbacks = DimensionCallbacks(
        build_prompt=_build_dimension_prompt,
        run_analysis=_run_dimension_analysis,
        parse_evidence=_parse_dimension_evidence,
    )
    if is_cache_v2_enabled():
        # Deferred import: avoids loading the cache stack on default runs.
        from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
        ev = process_dimension_with_cache(config, dimension, idx, ctx, callbacks)
    else:
        ev = process_dimension_with_subagents(config, dimension, idx, ctx, callbacks)

    if ev is None:
        log_warning(f"[{idx}/{ctx.total}] {dimension} — no valid evidence, skipping")
        return None

    _save_dimension_fingerprint(config, dimension)
    if emit_log:
        _log_dimension_result(ev, dimension, idx, ctx.total)
    return ev


def _run_dimension_incremental(
    config: RunConfig, dimension: str, idx: int, ctx: _AnalysisContext,
) -> Evidence | None:
    """Incremental path: detect changes, carry forward, analyze only changed files."""
    # Deferred import: circular dependency _dimension_ops → _incremental_orchestrator → _incremental_phases → _dimension_ops
    from quodeq.analysis._incremental_orchestrator import run_dimension_incremental
    return run_dimension_incremental(config, dimension, idx, ctx)
