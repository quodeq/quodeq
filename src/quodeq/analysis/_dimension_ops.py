"""Dimension orchestration: single-dimension processing and logging.

V2 (content-addressed cache) is the canonical path. Per-file cache
entries are written by ``persist_dispatch_results`` after dispatch;
no separate per-dimension fingerprint file is required.
"""
from __future__ import annotations

from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis._dimension_steps import (
    _build_dimension_prompt,
    _parse_dimension_evidence,
    _run_dimension_analysis,
)
from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
from quodeq.analysis.subagents.runner import DimensionCallbacks
from quodeq.core.evidence.model import Evidence
from quodeq.engine._runner_markers import emit_marker
from quodeq.shared.logging import log_info, log_success, log_warning


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
    ev = process_dimension_with_cache(config, dimension, idx, ctx, callbacks)

    if ev is None:
        log_warning(f"[{idx}/{ctx.total}] {dimension} — no valid evidence, skipping")
        return None

    if emit_log:
        _log_dimension_result(ev, dimension, idx, ctx.total)
    return ev


def _run_dimension_incremental(
    config: RunConfig, dimension: str, idx: int, ctx: _AnalysisContext,
) -> Evidence | None:
    """Incremental dimension path — V2 cache owns change detection.

    V1's classify_files + carry-forward + phase1 + backfill + finalize
    is gone (B6). The ``(incremental)`` log line is emitted by the
    caller in ``_loops.run_incremental_loop``.
    """
    return _process_single_dimension(config, dimension, idx, ctx, emit_log=False)
