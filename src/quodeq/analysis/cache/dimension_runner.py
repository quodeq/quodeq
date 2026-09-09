"""V2 cache-aware dimension processor — composes B4 helpers with the
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
cached, when migrating a long-lived V1 install to V2; B6 cleanup removes
V1's carry-forward once the V1 path is deleted.

Cache-replay lives in ``_replay.py``; the persist-watcher body, its persist
callable and the hoisted provenance-hash computation live in
``_persist_watcher.py``; the pre-dispatch setup (cache backend, trust model,
file listing, classification) lives in ``_dimension_context.py``.
``threading.Thread``/``threading.Event()`` stay in helpers defined here,
since ``mock.patch`` resolves where a name is used.
"""
from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from quodeq.analysis._evidence_parser import parse_evidence_from_jsonl
from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis.cache._dimension_context import (
    _CacheContext,
    _prepare_cache_context,
)
from quodeq.analysis.cache._failure_streak import (
    CircuitBreakerError,
    FailureStreakWatcher,
)
from quodeq.analysis.cache._persist_watcher import (
    _PERSIST_INTERVAL_S,
    _make_persist_fn,
    _periodic_persist,
    _resolve_failure_streak_threshold,
)
from quodeq.analysis.cache._replay import (
    _compute_files_read,
    _emit_cached_findings,  # noqa: F401 -- re-export
    _evidence_dir,
    _write_findings,
)
from quodeq.analysis.cache.backend import CacheBackend
from quodeq.analysis.subagents.runner import (
    DimensionCallbacks,
    process_dimension_with_subagents,
)
from quodeq.config.analysis_env import failure_streak_override
from quodeq.core.evidence.model import Evidence
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.data.ports.events import EventEmitter

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _MissDispatch:
    """The dispatcher call the miss path makes, bundled so the watcher
    wrapper below stays inside the parameter budget.
    """

    miss_config: RunConfig
    idx: int
    ctx: _AnalysisContext
    callbacks: DimensionCallbacks
    dispatcher: Callable[..., Evidence | None]
    log: LogSink


def _handle_all_hits(
    config: RunConfig, dim_id: str, ctx: _AnalysisContext, cctx: _CacheContext,
    writer_factory: Callable[[Path], EventEmitter] | None,
) -> Evidence | None:
    """All-hits short-circuit: no dispatch needed. Appends (not overwrites)
    since a dim may run multiple times in the same run (e.g. V1's backfill
    phase); dedup after handles overlap from a same-run repeat."""
    from quodeq.analysis.subagents.jsonl_utils import deduplicate_jsonl
    _write_findings(
        cctx.jsonl, cctx.classify.cached_findings, append=True,
        unconsolidated=cctx.classify.unconsolidated_findings,
        trust_model=cctx.trust_model, writer_factory=writer_factory,
    )
    if cctx.jsonl.exists():
        deduplicate_jsonl(cctx.jsonl)
    return parse_evidence_from_jsonl(
        config, dim_id, ctx, cctx.jsonl,
        files_read=_compute_files_read(cctx.classify, cctx.jsonl, cctx.files),
    )


def _prepare_miss_dispatch(
    config: RunConfig, dim_id: str, cctx: _CacheContext,
    writer_factory: Callable[[Path], EventEmitter] | None,
) -> RunConfig:
    """Build the dispatcher's file-filtered config, pre-write any cached
    findings, and persist the miss-key sidecar the discard path needs."""
    classify = cctx.classify
    miss_options = replace(config.options, incremental_file_filter=set(classify.misses))
    miss_config = replace(config, options=miss_options)
    if classify.cached_findings or classify.unconsolidated_findings:
        _write_findings(
            cctx.jsonl, classify.cached_findings, append=True,
            unconsolidated=classify.unconsolidated_findings,
            trust_model=cctx.trust_model, writer_factory=writer_factory,
        )
    sidecar = _evidence_dir(config) / f"{dim_id}_dispatch_keys.json"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps(classify.miss_keys, indent=2), encoding="utf-8")
    return miss_config


def _start_watchers(
    config: RunConfig, dim_id: str, cctx: _CacheContext, persist_interval_s: float,
) -> tuple[threading.Event, threading.Thread, FailureStreakWatcher]:
    """Start the periodic-persist watcher (safety net only; on_file_done
    already persists synchronously) and the failure-streak breaker.
    Creates the evidence JSONL up front, when absent, so the breaker's
    first poll doesn't warn about a missing file."""
    stop_event = threading.Event()
    persist_fn = _make_persist_fn(
        config, dim_id, cctx.jsonl, cctx.classify, cctx.cache, stop_event,
    )
    watcher = threading.Thread(
        target=_periodic_persist,
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
        threshold=_resolve_failure_streak_threshold(
            config.options, override=failure_streak_override(),
        ),
    )
    breaker.start()
    return stop_event, watcher, breaker


def _handle_breaker_trip(
    config: RunConfig, dim_id: str, ctx: _AnalysisContext, cctx: _CacheContext,
) -> Evidence:
    """Salvage the completed-so-far JSONL instead of discarding the whole
    dimension, flagging failure_streak. Raises when there is nothing to
    salvage, so the dim is marked INCOMPLETE as before."""
    if cctx.jsonl.exists():
        salvaged = parse_evidence_from_jsonl(
            config, dim_id, ctx, cctx.jsonl,
            files_read=_compute_files_read(cctx.classify, cctx.jsonl, cctx.files),
        )
        if salvaged is not None and salvaged.principles:
            salvaged.exit_reason = "failure_streak"
            return salvaged
    raise CircuitBreakerError("circuit_breaker")


def _handle_dispatch_result(
    config: RunConfig, dim_id: str, ctx: _AnalysisContext, cctx: _CacheContext,
    miss_evidence: Evidence | None,
) -> Evidence | None:
    """Finalize Evidence after a normal (non-tripped) dispatch return,
    re-parsing the JSONL so files_read reflects hits + misses."""
    if miss_evidence is None:
        replayed_anything = bool(
            cctx.classify.cached_findings or cctx.classify.unconsolidated_findings
        )
        if replayed_anything and cctx.jsonl.exists():
            return parse_evidence_from_jsonl(
                config, dim_id, ctx, cctx.jsonl,
                files_read=_compute_files_read(
                    cctx.classify, cctx.jsonl, cctx.files,
                ),
            )
        return None
    return parse_evidence_from_jsonl(
        config, dim_id, ctx, cctx.jsonl,
        files_read=_compute_files_read(cctx.classify, cctx.jsonl, cctx.files),
    )


def _dispatch_misses_with_watchers(
    config: RunConfig, dim_id: str, cctx: _CacheContext,
    dispatch: _MissDispatch, persist_interval_s: float,
) -> Evidence | None:
    """Dispatch the misses under the periodic-persist watcher and the
    failure-streak breaker, then finalize Evidence from the JSONL."""
    stop_event, watcher, breaker = _start_watchers(
        config, dim_id, cctx, persist_interval_s,
    )
    try:
        miss_evidence = dispatch.dispatcher(
            dispatch.miss_config, dim_id, dispatch.idx, dispatch.ctx,
            dispatch.callbacks, log=dispatch.log,
        )
    finally:
        # No join timeout (c88be50e regression: a capped join dropped the
        # final persist tick on long dims). Breaker keeps its own 5s cap.
        stop_event.set()
        watcher.join()
        breaker.stop_and_join(timeout=5.0)
    if breaker.trip_event is not None:
        return _handle_breaker_trip(config, dim_id, dispatch.ctx, cctx)
    return _handle_dispatch_result(
        config, dim_id, dispatch.ctx, cctx, miss_evidence,
    )


def process_dimension_with_cache(
    config: RunConfig, dim_id: str, idx: int, ctx: _AnalysisContext,
    callbacks: DimensionCallbacks,
    *,
    cache: CacheBackend | None = None,
    dispatcher: Callable[..., Evidence | None] = process_dimension_with_subagents,
    persist_interval_s: float = _PERSIST_INTERVAL_S,
    writer_factory: Callable[[Path], EventEmitter] | None = None,
    log: LogSink = NULL_LOG,
) -> Evidence | None:
    """V2 entry point — content-addressed cache replaces V1 change
    detection. Falls through to *dispatcher* when there's no source-file
    list to classify (matches V1's no-files fallback)."""
    cctx = _prepare_cache_context(config, dim_id, cache)
    if cctx is None:
        return dispatcher(config, dim_id, idx, ctx, callbacks, log=log)

    if not cctx.classify.misses:
        return _handle_all_hits(config, dim_id, ctx, cctx, writer_factory)

    dispatch = _MissDispatch(
        miss_config=_prepare_miss_dispatch(config, dim_id, cctx, writer_factory),
        idx=idx, ctx=ctx, callbacks=callbacks, dispatcher=dispatcher, log=log,
    )
    return _dispatch_misses_with_watchers(
        config, dim_id, cctx, dispatch, persist_interval_s,
    )
