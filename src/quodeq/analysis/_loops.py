"""Dimension loop orchestrators - run dimensions sequentially or incrementally."""
from __future__ import annotations

import json
from collections.abc import Mapping

from quodeq.analysis._dim_order import apply_dim_deadline
from quodeq.analysis._drop_stats import report_run_drop_stats
from quodeq.analysis.run_types import RunConfig, AnalysisContext
from quodeq.analysis.runner_markers import emit_marker
from quodeq.core.evidence.model import Evidence
from quodeq.core.observability import LogSink
from quodeq.core.run.dimensions import DimState
from quodeq.analysis._loop_state import (
    DimTransition,
    run_dir_for,
    safe_write_dim_state,
    interruption_reason,
    silence_broken_stdout,
)
from quodeq.analysis._loop_guards import (
    raise_on_fatal_cancel,
    check_zero_findings,
    check_model_reachable,
)
from quodeq.analysis._loop_steps import (
    LoopDeps,
    LoopRun,
    finalize_dim_result,
    loop_should_stop,
    run_one_incremental_dim,
)


def _run_post_loop_guards(
    config: RunConfig, result: dict[str, Evidence],
    skipped_count: int, log: LogSink,
) -> None:
    """Drop-stats report + the fatal-cancel/zero-findings/reachability guards.

    Drop stats run before any guard raises: a high drop ratio and a
    worthless run often co-occur, so the summary must land either way. The
    ``drop_stats`` dashboard marker is emitted here (not inside
    ``report_run_drop_stats``) -- this loop is the composition root for
    that seam, mirroring the "reads == 0" no-op rule the report itself uses.

    Reads the run's own drop counter (``config.drop_counter``) rather than
    taking one as a parameter, so every dimension loop of this run reports
    the same shared accumulator.
    """
    stats = report_run_drop_stats(config.drop_counter, log=log)
    if stats.parsed:
        emit_marker(
            "drop_stats",
            dropped=stats.dropped, kept=stats.kept, ratio=round(stats.ratio, 4),
        )
    raise_on_fatal_cancel(run_dir_for(config), log=log)
    check_zero_findings(
        result, config.source_file_count, skipped_count,
        incremental_filter_active=config.options.incremental_file_filter is not None
            or config.options.skip_scoring,
    )
    check_model_reachable(run_dir_for(config), result)


def run_incremental_loop(
    config: RunConfig, dimensions: list[str], ctx: AnalysisContext, deps: LoopDeps,
    *, dim_counts: Mapping[str, int] | None = None,
) -> dict[str, Evidence]:
    """Run incremental per-dimension analysis.

    ``deps.runner.run(config, dim, idx, ctx, emit_log=False)`` is used for
    the incremental path (the loop emits its own ``analyzing`` marker with
    an "(incremental)" suffix and logs the result itself); the full-scan
    fallback (see ``_dispatch_incremental_dim``) uses ``emit_log=True`` so
    the runner emits its own analyzing marker and success log.

    Each dimension gets its own slice of the remaining budget, sized by its
    pending file count from ``dim_counts`` (see ``_dim_order``), so a
    truncated run no longer always cuts the last dimension short. Per-dim
    scoring (``on_dimension_done``) runs inside the loop and so sees its
    dimension's slice; the run-level deadline is restored afterwards so the
    post-loop guards see the run budget, not the last dimension's slice.
    """
    log = deps.log
    result: dict[str, Evidence] = {}
    log.info(f"[loop] incremental: {len(dimensions)} dim(s) to process: {', '.join(dimensions)}")
    run = LoopRun(deps=deps, result=result)
    run_deadline = getattr(config.options, "deadline_at", None)
    config.options.run_deadline_at = run_deadline
    try:
        for idx, dimension in enumerate(dimensions, 1):
            apply_dim_deadline(config, dimensions[idx - 1:], run_deadline, dim_counts)
            if run_one_incremental_dim(config, dimension, idx, ctx, run):
                break
    # This restore would also discard a ratchet from
    # ``_pool_launcher._extend_run_deadline``, which only fires when
    # time_limit is None -- mutually exclusive with slicing, since a None
    # time_limit leaves deadline_at None. That changes if an outer caller
    # ever pre-sets deadline_at together with a time limit.
    finally:
        config.options.deadline_at = run_deadline
        config.options.run_deadline_at = None
    log.info(
        f"[loop] incremental finished: processed {len(result)} of {len(dimensions)} dim(s) "
        f"({', '.join(result) if result else 'none'})",
    )
    _run_post_loop_guards(config, result, 0, log)
    return result


def _dispatch_per_dim(
    config: RunConfig, dimension: str, idx: int, ctx: AnalysisContext, deps: LoopDeps,
) -> Evidence | None:
    """Run one dimension (full scan). Returns the Evidence, or None if skipped.

    On any caught exception, or a clean ``None`` return from the runner, this
    writes the dim's ``INCOMPLETE`` state (with the reason keyed off the real
    exception -- ``interruption_reason`` special-cases ``FatalProviderError``
    and ``CircuitBreakerError``, both of which surface here) and logs the
    "completed iteration" line itself, so the exception never needs to leave
    this function.
    """
    log = deps.log
    run_dir = run_dir_for(config)

    def _skip(reason: str, exc: BaseException | None = None) -> None:
        """Mark the dim INCOMPLETE and log the iteration as skipped for *reason*."""
        safe_write_dim_state(
            run_dir, dimension,
            DimTransition(DimState.INCOMPLETE, reason=interruption_reason(exc)), log=log,
        )
        log.info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (skipped: {reason})")

    try:
        ev = deps.runner.run(config, dimension, idx, ctx, emit_log=True)
    except BrokenPipeError as exc:
        silence_broken_stdout()
        _skip("broken pipe", exc)
        return None
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        log.warning(f"[{idx}/{ctx.total}] {dimension} - failed: {exc}")
        _skip(type(exc).__name__, exc)
        return None
    except Exception as exc:  # noqa: BLE001
        # Don't let an exotic exception class drop the rest of the loop
        # silently. Log + count as skipped + continue so we get the trail.
        log.warning(
            f"[loop] {dimension} - unexpected exception "
            f"{type(exc).__name__}: {exc} - skipping dim, continuing loop",
        )
        _skip("unexpected", exc)
        return None
    if ev is None:
        _skip("ev=None")
        return None
    return ev


def _run_one_dimension(
    config: RunConfig, dimension: str, idx: int, ctx: AnalysisContext, run: LoopRun,
) -> Evidence | None:
    """Take one dimension through RUNNING -> analysis -> finalized.

    Returns None when the dimension was skipped; ``_dispatch_per_dim`` has
    already written its INCOMPLETE state and logged the reason.
    """
    run_dir = run_dir_for(config)
    safe_write_dim_state(run_dir, dimension, DimTransition(DimState.RUNNING), log=run.deps.log)
    ev = _dispatch_per_dim(config, dimension, idx, ctx, run.deps)
    if ev is None:
        return None
    finalize_dim_result(run_dir, dimension, ev, run)
    return ev


def run_per_dimension_loop(
    config: RunConfig, dimensions: list[str], ctx: AnalysisContext, deps: LoopDeps,
) -> dict[str, Evidence]:
    """Per-dimension loop (fallback or single-dimension).

    ``deps.runner.run(config, dim, idx, ctx, emit_log=True)`` is used so the
    runner emits its own analyzing/scoring markers and success log.
    """
    log = deps.log
    result: dict[str, Evidence] = {}
    run = LoopRun(deps=deps, result=result)
    skipped_count = 0
    log.info(f"[loop] per-dimension: {len(dimensions)} dim(s) to process: {', '.join(dimensions)}")
    for idx, dimension in enumerate(dimensions, 1):
        log.info(f"[loop] entering iteration {idx}/{ctx.total} for {dimension}")
        if loop_should_stop(config, dimension, log):
            break
        if _run_one_dimension(config, dimension, idx, ctx, run) is None:
            skipped_count += 1
            continue
        log.info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (ev=set)")
    log.info(
        f"[loop] per-dimension finished: processed {len(result)} of {len(dimensions)} dim(s) "
        f"({', '.join(result) if result else 'none'}, {skipped_count} skipped)",
    )
    _run_post_loop_guards(config, result, skipped_count, log)
    return result
