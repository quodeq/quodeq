"""V2 cache-aware dimension processor — composes the cache helpers with the
existing dispatcher boundary.

Flow: list source files -> classify via cache (hits return findings directly, misses go to
the dispatcher) -> all-hits short-circuits straight to JSONL + Evidence -> otherwise
dispatch misses via process_dimension_with_subagents (file filter restricted to misses) ->
persist new findings per-file -> if there were also hits, append cached findings to the
JSONL and re-parse for the final Evidence.

This sits *above* the existing dispatcher — V1's machinery (carry-forward, fingerprint,
queue salvage) still runs for dispatched files. The cache supersedes V1's incrementality
decisions but keeps the proven dispatch path intact.

Known limitation: V1 carry-forward can duplicate findings V2 has already
cached, when migrating a long-lived V1 install to V2; this is cleaned up by
removing V1's carry-forward once the V1 path is deleted.

Cache-replay lives in ``_replay.py``; the persist-watcher body, its persist
callable and the provenance-hash computation live in
``_persist_watcher.py``; the pre-dispatch setup (cache backend, trust model,
file listing, classification) lives in ``_dimension_context.py``.
``threading.Thread``/``threading.Event()`` stay in helpers defined here,
since ``mock.patch`` resolves where a name is used.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace

from quodeq.analysis.evidence_parser import parse_evidence_from_jsonl
from quodeq.analysis.run_types import RunConfig, AnalysisContext
from quodeq.analysis.errors import REASON_CIRCUIT_BREAKER
from quodeq.core.run.exit_reason import ExitReason
from quodeq.analysis.cache._dimension_context import (
    CacheContext,
    prepare_cache_context,
)
from quodeq.analysis.cache.failure_streak import (
    STOP_JOIN_TIMEOUT_S,
    CircuitBreakerError,
    FailureStreakWatcher,
)
from quodeq.analysis.cache._persist_watcher import (
    PERSIST_INTERVAL_S,
    make_persist_fn,
    periodic_persist,
    resolve_failure_streak_threshold,
)
from quodeq.analysis.cache._replay import (
    compute_files_read,
    emit_cached_findings,  # noqa: F401 -- re-export
    write_dispatch_keys_sidecar,
    write_findings,
)
from quodeq.analysis.cache.backend import CacheBackend
from quodeq.analysis.subagents.runner import (
    DimensionCallbacks,
    process_dimension_with_subagents,
)
from quodeq.core.evidence.model import Evidence

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CacheRunOptions:
    """How ``process_dimension_with_cache`` dispatches and persists one run.

    ``callbacks`` carries the single-agent fallback steps and the log sink
    the dispatcher writes to; ``cache`` is the run's shared backend (None
    lets the cache context default to its own ``LocalFileBackend``);
    ``dispatcher`` and ``persist_interval_s`` are the test seams for the
    miss path and the periodic-persist watcher.
    """

    callbacks: DimensionCallbacks
    cache: CacheBackend | None = None
    dispatcher: Callable[..., Evidence | None] = process_dimension_with_subagents
    persist_interval_s: float = PERSIST_INTERVAL_S


@dataclass(frozen=True)
class _MissDispatch:
    """The dispatcher call the miss path makes, bundled so the watcher
    wrapper below stays inside the parameter budget.
    """

    miss_config: RunConfig
    idx: int
    ctx: AnalysisContext
    callbacks: DimensionCallbacks
    dispatcher: Callable[..., Evidence | None]


def _parse_dim_jsonl(
    config: RunConfig, ctx: AnalysisContext, cctx: CacheContext,
) -> Evidence | None:
    """Parse the dim's findings JSONL, crediting the files it actually read."""
    return parse_evidence_from_jsonl(
        config, ctx, cctx.jsonl,
        files_read=compute_files_read(cctx.classify, cctx.jsonl, cctx.files),
    )


def _handle_all_hits(
    config: RunConfig, ctx: AnalysisContext, cctx: CacheContext,
) -> Evidence | None:
    """All-hits short-circuit: no dispatch needed. Appends (not overwrites)
    since a dim may run multiple times in the same run (e.g. V1's backfill
    phase); dedup after handles overlap from a same-run repeat."""
    from quodeq.analysis.subagents.jsonl_utils import deduplicate_jsonl
    write_findings(cctx.jsonl, cctx.classify, append=True, trust_model=cctx.trust_model)
    if cctx.jsonl.exists():
        deduplicate_jsonl(cctx.jsonl)
    return _parse_dim_jsonl(config, ctx, cctx)


def _prepare_miss_dispatch(config: RunConfig, dim_id: str, cctx: CacheContext) -> RunConfig:
    """Build the dispatcher's file-filtered config, pre-write any cached
    findings, and persist the miss-key sidecar the discard path needs."""
    classify = cctx.classify
    miss_options = replace(config.options, incremental_file_filter=set(classify.misses))
    miss_config = replace(config, options=miss_options)
    if classify.cached_findings or classify.unconsolidated_findings:
        write_findings(cctx.jsonl, classify, append=True, trust_model=cctx.trust_model)
    write_dispatch_keys_sidecar(config, dim_id, classify.miss_keys)
    return miss_config


def _start_watchers(
    config: RunConfig, dim_id: str, cctx: CacheContext, persist_interval_s: float,
) -> tuple[threading.Event, threading.Thread, FailureStreakWatcher]:
    """Start the periodic-persist watcher (safety net only; on_file_done
    already persists synchronously) and the failure-streak breaker.
    Creates the evidence JSONL up front, when absent, so the breaker's
    first poll doesn't warn about a missing file."""
    stop_event = threading.Event()
    persist_fn = make_persist_fn(config, dim_id, cctx, stop_event)
    watcher = threading.Thread(
        target=periodic_persist,
        args=(stop_event, persist_fn, persist_interval_s, _logger.warning),
        daemon=True,
        name=f"v2-cache-persist-{dim_id}",
    )
    watcher.start()

    cctx.jsonl.parent.mkdir(parents=True, exist_ok=True)
    if not cctx.jsonl.exists():
        cctx.jsonl.touch()

    breaker = FailureStreakWatcher(
        cctx.jsonl,
        # The CLI already folded QUODEQ_FAILURE_STREAK into the options.
        threshold=resolve_failure_streak_threshold(config.options),
    )
    breaker.start()
    return stop_event, watcher, breaker


def _handle_breaker_trip(
    config: RunConfig, ctx: AnalysisContext, cctx: CacheContext,
) -> Evidence:
    """Salvage the completed-so-far JSONL instead of discarding the whole
    dimension, flagging failure_streak. Raises when there is nothing to
    salvage, so the dim is marked INCOMPLETE as before."""
    if cctx.jsonl.exists():
        salvaged = _parse_dim_jsonl(config, ctx, cctx)
        if salvaged is not None and salvaged.principles:
            salvaged.exit_reason = ExitReason.FAILURE_STREAK
            return salvaged
    raise CircuitBreakerError(REASON_CIRCUIT_BREAKER)


def _handle_dispatch_result(
    config: RunConfig, ctx: AnalysisContext, cctx: CacheContext,
    miss_evidence: Evidence | None,
) -> Evidence | None:
    """Finalize Evidence after a normal (non-tripped) dispatch return,
    re-parsing the JSONL so files_read reflects hits + misses."""
    if miss_evidence is None:
        replayed_anything = bool(
            cctx.classify.cached_findings or cctx.classify.unconsolidated_findings
        )
        if replayed_anything and cctx.jsonl.exists():
            return _parse_dim_jsonl(config, ctx, cctx)
        return None
    return _parse_dim_jsonl(config, ctx, cctx)


def _dispatch_misses_with_watchers(
    config: RunConfig, dim_id: str, cctx: CacheContext,
    dispatch: _MissDispatch, persist_interval_s: float,
) -> Evidence | None:
    """Dispatch the misses under the periodic-persist watcher and the
    failure-streak breaker, then finalize Evidence from the JSONL."""
    stop_event, watcher, breaker = _start_watchers(
        config, dim_id, cctx, persist_interval_s,
    )
    try:
        miss_evidence = dispatch.dispatcher(
            dispatch.miss_config, dim_id, dispatch.idx, dispatch.ctx, dispatch.callbacks,
        )
    finally:
        # No join timeout (c88be50e regression: a capped join dropped the
        # final persist tick on long dims). Breaker keeps its own 5s cap.
        stop_event.set()
        watcher.join()
        breaker.stop_and_join(timeout=STOP_JOIN_TIMEOUT_S)
    if breaker.trip_event is not None:
        return _handle_breaker_trip(config, dispatch.ctx, cctx)
    return _handle_dispatch_result(
        config, dispatch.ctx, cctx, miss_evidence,
    )


def process_dimension_with_cache(
    config: RunConfig, dim_id: str, idx: int, ctx: AnalysisContext, opts: CacheRunOptions,
) -> Evidence | None:
    """V2 entry point — content-addressed cache replaces V1 change
    detection. Falls through to ``opts.dispatcher`` when there's no
    source-file list to classify (matches V1's no-files fallback)."""
    cctx = prepare_cache_context(config, dim_id, opts.cache, log=opts.callbacks.log)
    if cctx is None:
        return opts.dispatcher(config, dim_id, idx, ctx, opts.callbacks)

    if not cctx.classify.misses:
        return _handle_all_hits(config, ctx, cctx)

    dispatch = _MissDispatch(
        miss_config=_prepare_miss_dispatch(config, dim_id, cctx),
        idx=idx, ctx=ctx, callbacks=opts.callbacks, dispatcher=opts.dispatcher,
    )
    return _dispatch_misses_with_watchers(
        config, dim_id, cctx, dispatch, opts.persist_interval_s,
    )
