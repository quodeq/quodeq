"""DimensionRunner: named seam for single-dimension analysis.

Owns the full per-dimension lifecycle: prompt building, AI dispatch,
evidence parsing, and the BrokenPipeError guard around the success log.

The ``callbacks`` parameter makes the dispatch steps injectable so tests
can exercise the orchestration logic (cache merging, broken-pipe guard,
emit_log behaviour) without calling real AI infrastructure.
"""
from __future__ import annotations

from dataclasses import replace

from quodeq.analysis.run_types import RunConfig, AnalysisContext
from quodeq.analysis.cache.backend import CacheBackend
from quodeq.analysis.cache.dimension_runner import CacheRunOptions, process_dimension_with_cache
from quodeq.analysis.checks.runner import apply_checks_for_run
from quodeq.analysis.subagents.runner import DimensionCallbacks
from quodeq.core.evidence.model import Evidence
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.analysis.runner_markers import emit_marker
from quodeq.shared.constants import CC_PHASE_ANALYZING, CC_PHASE_SCORING


def _default_callbacks() -> DimensionCallbacks:
    from quodeq.analysis._dimension_steps import (
        build_dimension_prompt,
        parse_dimension_evidence,
        run_dimension_analysis,
    )
    return DimensionCallbacks(
        build_prompt=build_dimension_prompt,
        run_analysis=run_dimension_analysis,
        parse_evidence=parse_dimension_evidence,
    )


class DimensionRunner:
    """Runs a single dimension end-to-end and returns its Evidence.

    Construct once per run (or per test) and call ``run()`` per dimension.
    Inject ``callbacks`` to replace the AI dispatch steps in tests.

    ``cache`` is the composition root's shared cache backend for the whole
    run; left ``None``, ``process_dimension_with_cache`` defaults to its own
    ``LocalFileBackend()`` (and runs the once-per-process cache maintenance)
    -- see ``_pipeline.py`` for the production wiring.

    ``log`` defaults to the silent :data:`NULL_LOG`; the composition root
    (``_pipeline.py``) injects ``SHARED_LOG`` so production keeps the colored
    console lines. The sink is threaded through the whole dimension chain
    (cache runner -> subagent dispatcher).
    """

    def __init__(
        self, callbacks: DimensionCallbacks | None = None,
        cache: CacheBackend | None = None,
        log: LogSink = NULL_LOG,
    ) -> None:
        self._opts = CacheRunOptions(
            callbacks=replace(callbacks or _default_callbacks(), log=log), cache=cache,
        )
        self._log = log

    def run(
        self,
        config: RunConfig,
        dim_id: str,
        idx: int,
        ctx: AnalysisContext,
        *,
        emit_log: bool = True,
    ) -> Evidence | None:
        """Analyze *dim_id* and return its Evidence, or None on failure."""
        if emit_log:
            emit_marker(CC_PHASE_ANALYZING, dimension=dim_id)
            self._log.info(f"→ [{idx}/{ctx.total}] Analyzing {dim_id}")

        ev = process_dimension_with_cache(config, dim_id, idx, ctx, self._opts)

        if ev is None:
            self._log.warning(f"[{idx}/{ctx.total}] {dim_id} — no valid evidence, skipping")
            return None

        # Requirements the standard marks as deterministically checkable are
        # answered here, from the whole import graph. They cannot come out of
        # the per-file cache the way an LLM finding does -- "does anything in
        # this project reach Flask" is not a property of any one file.
        checked = apply_checks_for_run(config, dim_id, ev)
        if checked:
            self._log.info(f"   {dim_id} — {checked} finding(s) from deterministic checks")

        if emit_log:
            # The dimension has analytically succeeded. Guard the success-log
            # line against BrokenPipeError (dashboard pipe can close at any
            # moment) so a logging failure doesn't mask a successful analysis.
            try:
                log_dimension_result(ev, dim_id, idx, ctx.total, log=self._log)
            except BrokenPipeError:
                from quodeq.analysis._loops import silence_broken_stdout  # noqa: PLC0415
                silence_broken_stdout()
        return ev


def log_dimension_result(
    ev: Evidence, dimension: str, idx: int, total: int, *,
    log: LogSink = NULL_LOG,
) -> None:
    """Emit the scoring marker and log the dimension's file and finding counts."""
    emit_marker(CC_PHASE_SCORING, dimension=dimension)
    violations = sum(len(pe.violations) for pe in ev.principles.values())
    compliances = sum(len(pe.compliance) for pe in ev.principles.values())
    log.success(f"[{idx}/{total}] {dimension} — {ev.files_read} files, {violations}v/{compliances}c")
