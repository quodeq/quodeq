"""Per-iteration step for the incremental dimension loop.

Split out of ``_loops.py`` (Task 22, M-MOD-6): ``run_incremental_loop``'s
per-dimension body, kept here so ``_loops.py`` stays under the 300-line size
ratchet. Imports back from ``_loops`` for the callees it absorbs
(``_dispatch_incremental_dim``, ``_finalize_dim_result``, ``_loop_should_stop``);
``run_incremental_loop`` imports this module back with a deferred import to
avoid a circular top-level import between the two.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable

from quodeq.analysis._loop_state import _interruption_reason, _run_dir_for, _safe_write_dim_state
from quodeq.analysis._loops import _dispatch_incremental_dim, _finalize_dim_result, _loop_should_stop
from quodeq.analysis._runner_markers import emit_marker
from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis.dimension_runner import DimensionRunner, _log_dimension_result
from quodeq.core.evidence.model import Evidence
from quodeq.core.observability import LogSink
from quodeq.data.fs.dimensions_state_store import DimState


@dataclass(frozen=True)
class _IncrementalDimDeps:
    """Loop-invariant collaborators for one incremental-loop iteration."""

    runner: DimensionRunner
    on_dimension_done: Callable[[str, Evidence], None] | None
    result: dict[str, Evidence]
    log: LogSink


def _run_one_incremental_dim(
    config: RunConfig, dimension: str, idx: int, ctx: _AnalysisContext,
    deps: _IncrementalDimDeps,
) -> bool:
    """Run one incremental-loop iteration for *dimension*.

    Returns True if the loop should stop before this dimension ran (deadline
    or cancellation reached), in which case the caller must break the loop
    without counting the iteration as completed.
    """
    log = deps.log
    log.info(f"[loop] entering iteration {idx}/{ctx.total} for {dimension}")
    if _loop_should_stop(config, dimension, log):
        return True
    run_dir = _run_dir_for(config)
    _safe_write_dim_state(run_dir, dimension, DimState.RUNNING, log=log)
    emit_marker("analyzing", dimension=dimension)
    log.info(f"-> [{idx}/{ctx.total}] Analyzing {dimension} (incremental)")
    ev, last_exc = _dispatch_incremental_dim(config, dimension, idx, ctx, runner=deps.runner, log=log)
    if ev:
        _finalize_dim_result(
            run_dir, dimension, ev, deps.on_dimension_done, deps.result, log,
            log_result=lambda ev=ev: _log_dimension_result(ev, dimension, idx, ctx.total, log=log),
        )
    else:
        _safe_write_dim_state(run_dir, dimension, DimState.INCOMPLETE, reason=_interruption_reason(last_exc), log=log)
    log.info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (ev={'set' if ev else 'None'})")
    return False
