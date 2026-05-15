"""DimensionRunner: named seam for single-dimension analysis.

Owns the full per-dimension lifecycle: prompt building, AI dispatch,
evidence parsing, and the BrokenPipeError guard around the success log.

The ``callbacks`` parameter makes the dispatch steps injectable so tests
can exercise the orchestration logic (cache merging, broken-pipe guard,
emit_log behaviour) without calling real AI infrastructure.
"""
from __future__ import annotations

from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
from quodeq.analysis.subagents.runner import DimensionCallbacks
from quodeq.core.evidence.model import Evidence
from quodeq.engine._runner_markers import emit_marker
from quodeq.shared.logging import log_info, log_success, log_warning


def _default_callbacks() -> DimensionCallbacks:
    from quodeq.analysis._dimension_steps import (
        _build_dimension_prompt,
        _parse_dimension_evidence,
        _run_dimension_analysis,
    )
    return DimensionCallbacks(
        build_prompt=_build_dimension_prompt,
        run_analysis=_run_dimension_analysis,
        parse_evidence=_parse_dimension_evidence,
    )


class DimensionRunner:
    """Runs a single dimension end-to-end and returns its Evidence.

    Construct once per run (or per test) and call ``run()`` per dimension.
    Inject ``callbacks`` to replace the AI dispatch steps in tests.
    """

    def __init__(self, callbacks: DimensionCallbacks | None = None) -> None:
        self._callbacks = callbacks or _default_callbacks()

    def run(
        self,
        config: RunConfig,
        dim_id: str,
        idx: int,
        ctx: _AnalysisContext,
        *,
        emit_log: bool = True,
    ) -> Evidence | None:
        """Analyze *dim_id* and return its Evidence, or None on failure."""
        if emit_log:
            emit_marker("analyzing", dimension=dim_id)
            log_info(f"→ [{idx}/{ctx.total}] Analyzing {dim_id}")

        ev = process_dimension_with_cache(config, dim_id, idx, ctx, self._callbacks)

        if ev is None:
            log_warning(f"[{idx}/{ctx.total}] {dim_id} — no valid evidence, skipping")
            return None

        if emit_log:
            # The dimension has analytically succeeded. Guard the success-log
            # line against BrokenPipeError (dashboard pipe can close at any
            # moment) so a logging failure doesn't mask a successful analysis.
            try:
                _log_dimension_result(ev, dim_id, idx, ctx.total)
            except BrokenPipeError:
                from quodeq.analysis._loops import _silence_broken_stdout  # noqa: PLC0415
                _silence_broken_stdout()
        return ev


def _log_dimension_result(ev: Evidence, dimension: str, idx: int, total: int) -> None:
    emit_marker("scoring", dimension=dimension)
    violations = sum(len(pe.violations) for pe in ev.principles.values())
    compliances = sum(len(pe.compliance) for pe in ev.principles.values())
    log_success(f"[{idx}/{total}] {dimension} — {ev.files_read} files, {violations}v/{compliances}c")
