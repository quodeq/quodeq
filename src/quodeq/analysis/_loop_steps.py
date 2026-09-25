"""Per-dimension steps shared by the dimension loops.

This module imports only downward (``_loop_state``, ``runner_markers``, ``run_types``, ``dimension_runner``,
core/data/shared) and never imports back from ``_loops`` -- ``_loops.py``
imports it at the top instead. ``loop_should_stop`` and ``finalize_dim_result``
live here because ``run_incremental_loop``'s per-iteration step
(``run_one_incremental_dim``) needs them and an import back into ``_loops``
would create a cycle; ``_loops.py``'s ``run_per_dimension_loop`` imports them
from here.
"""
from __future__ import annotations

import time
from copy import copy
from dataclasses import dataclass, replace
from collections.abc import Callable
from pathlib import Path

from quodeq.analysis._drop_stats import DropStatsCounter
from quodeq.analysis._loop_state import (
    DimTransition,
    interruption_reason,
    run_dir_for,
    safe_write_dim_state,
    silence_broken_stdout,
)
from quodeq.analysis.runner_markers import emit_marker
from quodeq.analysis.run_types import RunConfig, AnalysisContext
from quodeq.analysis.dimension_runner import DimensionRunner, log_dimension_result
from quodeq.shared.constants import CC_PHASE_ANALYZING
from quodeq.core.evidence.model import Evidence
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.run.dimensions import DimState
from quodeq.shared import cancellation


@dataclass(frozen=True, slots=True)
class LoopDeps:
    """Loop-invariant collaborators for one dimension loop.

    ``runner`` analyses a dimension; ``on_dimension_done`` receives each
    finished dimension's Evidence (scoring, in production); ``log`` is the
    loop's sink and ``drop_counter`` the per-run drop-stats aggregate the
    loop reports once it finishes.
    """

    runner: DimensionRunner
    on_dimension_done: Callable[[str, Evidence], None] | None = None
    log: LogSink = NULL_LOG
    drop_counter: DropStatsCounter | None = None


def default_loop_deps(
    runner: DimensionRunner, on_dimension_done: Callable[[str, Evidence], None] | None,
    log: LogSink = NULL_LOG,
) -> LoopDeps:
    """The dependency bundle a dimension loop is driven with."""
    return LoopDeps(runner=runner, on_dimension_done=on_dimension_done, log=log)


@dataclass(frozen=True, slots=True)
class LoopRun:
    """One loop's collaborators plus the Evidence accumulator it returns."""

    deps: LoopDeps
    result: dict[str, Evidence]


def loop_should_stop(config: RunConfig, dimension: str, log: LogSink) -> bool:
    """True if the loop should stop before ``dimension`` (deadline or cancel).

    Both cases leave the remaining dims PENDING (they never went RUNNING),
    so no dim-state write is needed here.
    """
    deadline = getattr(config.options, "deadline_at", None)
    if deadline is not None and time.monotonic() >= deadline:
        log.info(f"[loop] deadline reached -- skipping {dimension} and remaining dims")
        return True
    if cancellation.is_cancelled():
        log.info(f"[loop] cancellation requested -- skipping {dimension} and remaining dims")
        return True
    return False


def _retry_dim_callback(dimension: str, ev: Evidence, run: LoopRun) -> None:
    """Retry ``on_dimension_done`` once after a BrokenPipeError.

    Stdout pipe to parent died mid-callback. Silence stdout/stderr, then
    retry the callback once: scoring callbacks like ``_score_dimension``
    write evaluation/<dim>.json to disk and are idempotent (overwrite). The
    previous "result kept" message was misleading - only the in-memory
    Evidence stayed, the persistent file write was lost with the exception.
    """
    log = run.deps.log
    on_dimension_done = run.deps.on_dimension_done
    silence_broken_stdout()
    run.result.setdefault(dimension, ev)
    if not on_dimension_done:
        log.warning(f"[loop] {dimension} - callback broken pipe, no retry needed, continuing loop")
        return
    try:
        on_dimension_done(dimension, ev)
        log.warning(
            f"[loop] {dimension} - callback broken pipe, "
            f"retried after silencing stdout, result persisted",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            f"[loop] {dimension} - callback retry after broken pipe raised "
            f"{type(exc).__name__}: {exc} - result NOT persisted, continuing loop",
        )


def finalize_dim_result(
    run_dir: Path | None, dimension: str, ev: Evidence, run: LoopRun,
    *, log_result: Callable[[], None] | None = None,
) -> None:
    """Write the DONE dim-state and run the ``on_dimension_done`` callback.

    Shared tail for a successfully-analysed dimension (``ev`` is non-None).
    ``log_result``, when given, is called first inside the try: the
    incremental loop uses it to log the dimension result itself (it runs
    the runner with ``emit_log=False``); the per-dimension loop passes None
    because the runner already logged with ``emit_log=True``.
    """
    log = run.deps.log
    safe_write_dim_state(
        run_dir, dimension, DimTransition(DimState.DONE, exit_reason=ev.exit_reason), log=log,
    )
    try:
        if log_result:
            log_result()
        run.result[dimension] = ev
        if run.deps.on_dimension_done:
            run.deps.on_dimension_done(dimension, ev)
    except BrokenPipeError:
        _retry_dim_callback(dimension, ev, run)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            f"[loop] {dimension} - callback raised "
            f"{type(exc).__name__}: {exc} - result kept, continuing loop",
        )
        run.result.setdefault(dimension, ev)


def _stdout_gone(exc: BrokenPipeError) -> tuple[None, BrokenPipeError]:
    """Silence the closed stdout and report the dimension as not run because of *exc*."""
    silence_broken_stdout()
    return None, exc


def _dispatch_incremental_dim(
    config: RunConfig, dimension: str, idx: int, ctx: AnalysisContext, deps: LoopDeps,
) -> tuple[Evidence | None, BaseException | None]:
    """Run one dimension incrementally, falling back to a full scan on failure.

    Returns ``(ev, last_exc)``: ``ev`` is the resulting Evidence (or None if
    both the incremental attempt and any fallback failed), ``last_exc`` is
    the most recent exception encountered (or None on success), used to
    pick the dim-state ``INCOMPLETE`` reason.
    """
    runner, log = deps.runner, deps.log
    try:
        return runner.run(config, dimension, idx, ctx, emit_log=False), None
    except BrokenPipeError as exc:
        return _stdout_gone(exc)
    except (OSError, KeyError, ValueError, RuntimeError) as exc:
        if cancellation.is_cancelled():
            # The run is being torn down (signal, breaker, fatal provider
            # error): a full-scan fallback would only spawn agents that
            # die immediately against the same dead provider.
            log.warning(
                f"[{idx}/{ctx.total}] {dimension} - incremental failed: {exc}; "
                f"run cancelled, skipping full-scan fallback",
            )
            return None, exc
        log.warning(f"[{idx}/{ctx.total}] {dimension} - incremental failed: {exc}, falling back to full")
        fallback_options = copy(config.options)
        fallback_options.incremental_file_filter = None
        fallback_config = replace(config, options=fallback_options)
        try:
            return runner.run(fallback_config, dimension, idx, ctx, emit_log=True), None
        except BrokenPipeError as inner_exc:
            return _stdout_gone(inner_exc)
        except Exception as inner_exc:  # noqa: BLE001
            return None, inner_exc
    except Exception as exc:  # noqa: BLE001
        # Loop-level diagnostic: an unanticipated exception class would
        # otherwise propagate up silently and the lifecycle would treat it
        # as failed without saying which dim. Log + swallow + continue so
        # subsequent dims still run; the surfaced log line gives us the
        # trail we need next time this happens.
        log.warning(
            f"[loop] {dimension} - unexpected exception "
            f"{type(exc).__name__}: {exc} - skipping dim, continuing loop",
        )
        return None, exc


def run_one_incremental_dim(
    config: RunConfig, dimension: str, idx: int, ctx: AnalysisContext, run: LoopRun,
) -> bool:
    """Run one incremental-loop iteration for *dimension*.

    Returns True if the loop should stop before this dimension ran (deadline
    or cancellation reached), in which case the caller must break the loop
    without counting the iteration as completed.
    """
    log = run.deps.log
    log.info(f"[loop] entering iteration {idx}/{ctx.total} for {dimension}")
    if loop_should_stop(config, dimension, log):
        return True
    run_dir = run_dir_for(config)
    safe_write_dim_state(run_dir, dimension, DimTransition(DimState.RUNNING), log=log)
    emit_marker(CC_PHASE_ANALYZING, dimension=dimension)
    log.info(f"-> [{idx}/{ctx.total}] Analyzing {dimension} (incremental)")
    ev, last_exc = _dispatch_incremental_dim(config, dimension, idx, ctx, run.deps)
    if ev:
        finalize_dim_result(
            run_dir, dimension, ev, run,
            log_result=lambda ev=ev: log_dimension_result(ev, dimension, idx, ctx.total, log=log),
        )
    else:
        safe_write_dim_state(
            run_dir, dimension,
            DimTransition(DimState.INCOMPLETE, reason=interruption_reason(last_exc)), log=log,
        )
    log.info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (ev={'set' if ev else 'None'})")
    return False
