"""Dimension loop orchestrators - run dimensions sequentially or incrementally."""
from __future__ import annotations

import json
import time
from copy import copy
from dataclasses import replace
from collections.abc import Callable
from pathlib import Path

from quodeq.analysis._drop_stats import DropStatsCounter, report_run_drop_stats
from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis.dimension_runner import DimensionRunner, _log_dimension_result
from quodeq.core.evidence.model import Evidence
from quodeq.analysis._runner_markers import emit_marker
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.shared import cancellation
from quodeq.data.fs.dimensions_state_store import DimState
from quodeq.analysis._loop_state import (
    _run_dir_for,
    _safe_write_dim_state,
    _interruption_reason,
    _silence_broken_stdout,
)
from quodeq.analysis._loop_guards import (
    _raise_on_fatal_cancel,
    check_zero_findings,
    check_model_reachable,
)


def _retry_dim_callback(
    dimension: str, ev: Evidence,
    on_dimension_done: Callable[[str, Evidence], None] | None,
    result: dict[str, Evidence], log: LogSink,
) -> None:
    """Retry ``on_dimension_done`` once after a BrokenPipeError.

    Stdout pipe to parent died mid-callback. Silence stdout/stderr, then
    retry the callback once: scoring callbacks like ``_score_dimension``
    write evaluation/<dim>.json to disk and are idempotent (overwrite). The
    previous "result kept" message was misleading - only the in-memory
    Evidence stayed, the persistent file write was lost with the exception.
    """
    _silence_broken_stdout()
    result.setdefault(dimension, ev)
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


def _finalize_dim_result(
    run_dir: Path | None, dimension: str, ev: Evidence,
    on_dimension_done: Callable[[str, Evidence], None] | None,
    result: dict[str, Evidence], log: LogSink,
    *, log_result: Callable[[], None] | None = None,
) -> None:
    """Write the DONE dim-state and run the ``on_dimension_done`` callback.

    Shared tail for a successfully-analysed dimension (``ev`` is non-None).
    ``log_result``, when given, is called first inside the try: the
    incremental loop uses it to log the dimension result itself (it runs
    the runner with ``emit_log=False``); the per-dimension loop passes None
    because the runner already logged with ``emit_log=True``.
    """
    _safe_write_dim_state(
        run_dir, dimension, DimState.DONE,
        exit_reason=ev.exit_reason, log=log,
    )
    try:
        if log_result:
            log_result()
        result[dimension] = ev
        if on_dimension_done:
            on_dimension_done(dimension, ev)
    except BrokenPipeError:
        _retry_dim_callback(dimension, ev, on_dimension_done, result, log)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            f"[loop] {dimension} - callback raised "
            f"{type(exc).__name__}: {exc} - result kept, continuing loop",
        )
        result.setdefault(dimension, ev)


def _loop_should_stop(config: RunConfig, dimension: str, log: LogSink) -> bool:
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


def _run_post_loop_guards(
    config: RunConfig, result: dict[str, Evidence],
    drop_counter: DropStatsCounter | None, skipped_count: int, log: LogSink,
) -> None:
    """Drop-stats report + the fatal-cancel/zero-findings/reachability guards.

    Drop stats run before any guard raises: a high drop ratio and a
    worthless run often co-occur, so the summary must land either way.
    """
    report_run_drop_stats(drop_counter)
    _raise_on_fatal_cancel(_run_dir_for(config), log=log)
    check_zero_findings(
        result, config.source_file_count, skipped_count,
        incremental_filter_active=config.options.incremental_file_filter is not None
            or config.options.skip_scoring,
    )
    check_model_reachable(_run_dir_for(config), result)


def _dispatch_incremental_dim(
    config: RunConfig, dimension: str, idx: int, ctx: _AnalysisContext,
    *, runner: DimensionRunner, log: LogSink,
) -> tuple[Evidence | None, BaseException | None]:
    """Run one dimension incrementally, falling back to a full scan on failure.

    Returns ``(ev, last_exc)``: ``ev`` is the resulting Evidence (or None if
    both the incremental attempt and any fallback failed), ``last_exc`` is
    the most recent exception encountered (or None on success), used to
    pick the dim-state ``INCOMPLETE`` reason.
    """
    try:
        return runner.run(config, dimension, idx, ctx, emit_log=False), None
    except BrokenPipeError as exc:
        _silence_broken_stdout()
        return None, exc
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
            _silence_broken_stdout()
            return None, inner_exc
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


def run_incremental_loop(
    config: RunConfig, dimensions: list[str], ctx: _AnalysisContext,
    *, runner: DimensionRunner,
    on_dimension_done: Callable[[str, Evidence], None] | None = None,
    log: LogSink = NULL_LOG,
    drop_counter: DropStatsCounter | None = None,
) -> dict[str, Evidence]:
    """Run incremental per-dimension analysis.

    ``runner.run(config, dim, idx, ctx, emit_log=False)`` is used for the
    incremental path (the loop emits its own ``analyzing`` marker with an
    "(incremental)" suffix and logs the result itself); the full-scan
    fallback (see ``_dispatch_incremental_dim``) uses ``emit_log=True`` so
    the runner emits its own analyzing marker and success log.
    """
    result: dict[str, Evidence] = {}
    log.info(f"[loop] incremental: {len(dimensions)} dim(s) to process: {', '.join(dimensions)}")
    for idx, dimension in enumerate(dimensions, 1):
        log.info(f"[loop] entering iteration {idx}/{ctx.total} for {dimension}")
        if _loop_should_stop(config, dimension, log):
            break
        run_dir = _run_dir_for(config)
        _safe_write_dim_state(run_dir, dimension, DimState.RUNNING, log=log)
        emit_marker("analyzing", dimension=dimension)
        log.info(f"-> [{idx}/{ctx.total}] Analyzing {dimension} (incremental)")
        ev, last_exc = _dispatch_incremental_dim(config, dimension, idx, ctx, runner=runner, log=log)
        if ev:
            _finalize_dim_result(
                run_dir, dimension, ev, on_dimension_done, result, log,
                log_result=lambda ev=ev: _log_dimension_result(ev, dimension, idx, ctx.total, log=log),
            )
        else:
            _safe_write_dim_state(run_dir, dimension, DimState.INCOMPLETE, reason=_interruption_reason(last_exc), log=log)
        log.info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (ev={'set' if ev else 'None'})")
    log.info(
        f"[loop] incremental finished: processed {len(result)} of {len(dimensions)} dim(s) "
        f"({', '.join(result) if result else 'none'})",
    )
    _run_post_loop_guards(config, result, drop_counter, 0, log)
    return result


def _dispatch_per_dim(
    config: RunConfig, dimension: str, idx: int, ctx: _AnalysisContext, run_dir: Path | None,
    *, runner: DimensionRunner, log: LogSink,
) -> Evidence | None:
    """Run one dimension (full scan). Returns the Evidence, or None if skipped.

    On any caught exception, or a clean ``None`` return from the runner, this
    writes the dim's ``INCOMPLETE`` state (with the reason keyed off the real
    exception -- ``_interruption_reason`` special-cases ``FatalProviderError``
    and ``CircuitBreakerError``, both of which surface here) and logs the
    "completed iteration" line itself, so the exception never needs to leave
    this function.
    """
    try:
        ev = runner.run(config, dimension, idx, ctx, emit_log=True)
    except BrokenPipeError as exc:
        _silence_broken_stdout()
        _safe_write_dim_state(run_dir, dimension, DimState.INCOMPLETE, reason=_interruption_reason(exc), log=log)
        log.info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (skipped: broken pipe)")
        return None
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        log.warning(f"[{idx}/{ctx.total}] {dimension} - failed: {exc}")
        _safe_write_dim_state(run_dir, dimension, DimState.INCOMPLETE, reason=_interruption_reason(exc), log=log)
        log.info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (skipped: {type(exc).__name__})")
        return None
    except Exception as exc:  # noqa: BLE001
        # Don't let an exotic exception class drop the rest of the loop
        # silently. Log + count as skipped + continue so we get the trail.
        log.warning(
            f"[loop] {dimension} - unexpected exception "
            f"{type(exc).__name__}: {exc} - skipping dim, continuing loop",
        )
        _safe_write_dim_state(run_dir, dimension, DimState.INCOMPLETE, reason=_interruption_reason(exc), log=log)
        log.info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (skipped: unexpected)")
        return None
    if ev is None:
        _safe_write_dim_state(run_dir, dimension, DimState.INCOMPLETE, reason=_interruption_reason(), log=log)
        log.info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (skipped: ev=None)")
        return None
    return ev


def run_per_dimension_loop(
    config: RunConfig, dimensions: list[str], ctx: _AnalysisContext,
    *, runner: DimensionRunner,
    on_dimension_done: Callable[[str, Evidence], None] | None = None,
    log: LogSink = NULL_LOG,
    drop_counter: DropStatsCounter | None = None,
) -> dict[str, Evidence]:
    """Per-dimension loop (fallback or single-dimension).

    ``runner.run(config, dim, idx, ctx, emit_log=True)`` is used so the
    runner emits its own analyzing/scoring markers and success log.
    """
    result: dict[str, Evidence] = {}
    skipped_count = 0
    log.info(f"[loop] per-dimension: {len(dimensions)} dim(s) to process: {', '.join(dimensions)}")
    for idx, dimension in enumerate(dimensions, 1):
        log.info(f"[loop] entering iteration {idx}/{ctx.total} for {dimension}")
        if _loop_should_stop(config, dimension, log):
            break
        run_dir = _run_dir_for(config)
        _safe_write_dim_state(run_dir, dimension, DimState.RUNNING, log=log)
        ev = _dispatch_per_dim(config, dimension, idx, ctx, run_dir, runner=runner, log=log)
        if ev is None:
            skipped_count += 1
            continue
        # ev is set - dim succeeded analytically.
        _finalize_dim_result(run_dir, dimension, ev, on_dimension_done, result, log)
        log.info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (ev=set)")
    log.info(
        f"[loop] per-dimension finished: processed {len(result)} of {len(dimensions)} dim(s) "
        f"({', '.join(result) if result else 'none'}, {skipped_count} skipped)",
    )
    _run_post_loop_guards(config, result, drop_counter, skipped_count, log)
    return result
