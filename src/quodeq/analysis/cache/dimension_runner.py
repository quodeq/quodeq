"""V2 cache-aware dimension processor — composes B4 helpers with the
existing dispatcher boundary.

Flow: list source files -> classify via cache (hits return findings
directly, misses go to the dispatcher) -> all-hits short-circuits
straight to JSONL + Evidence -> otherwise dispatch misses via
process_dimension_with_subagents (file filter restricted to misses) ->
persist new findings per-file -> if there were also hits, append cached
findings to the JSONL and re-parse for the final Evidence.

This sits *above* the existing dispatcher — V1's machinery (carry-
forward, fingerprint, queue salvage) still runs for dispatched files.
The cache supersedes V1's incrementality decisions but keeps the proven
dispatch path intact.

Known limitation: V1 carry-forward can duplicate findings V2 has
already cached, when migrating a long-lived V1 install to V2; B6
cleanup removes V1's carry-forward once the V1 path is deleted.

Cache-replay lives in ``_replay.py``; the persist-watcher body lives in
``_persist_watcher.py``. ``emit_marker`` and the
``threading.Thread``/``threading.Event()`` constructions stay in helpers
defined here, since a ``mock.patch`` target resolves where a name is
used, not where it is implemented.
"""
from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from quodeq.analysis._evidence_parser import parse_evidence_from_jsonl
from quodeq.analysis._runner_markers import emit_marker
from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis.cache._failure_streak import (
    CircuitBreakerError,
    FailureStreakWatcher,
)
from quodeq.analysis.cache._persist_watcher import (
    _PERSIST_INTERVAL_S,
    _periodic_persist,
    _resolve_failure_streak_threshold,
)
from quodeq.analysis.cache._replay import (
    _compute_files_read,
    _emit_cached_findings,  # noqa: F401 -- re-export
    _evidence_dir,
    _jsonl_path,
    _write_findings,
    _write_replayed_keys_sidecar,
)
from quodeq.analysis.cache.backend import CacheBackend
from quodeq.analysis.cache.dimension_helpers import (
    ClassifyResult,
    build_cache_key_for_file,
    classify_files_via_cache,
    format_provenance_drift,
    persist_dispatch_results,
)
from quodeq.analysis.cache.gc import maybe_collect_legacy_entries
from quodeq.analysis.cache.local import LocalFileBackend
from quodeq.analysis.subagents._source_files import _list_source_files
from quodeq.analysis.subagents.runner import (
    DimensionCallbacks,
    process_dimension_with_subagents,
)
from quodeq.config.analysis_env import failure_streak_override
from quodeq.context.trust_model import TrustModel, resolve_trust_model
from quodeq.core.evidence.model import Evidence
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.data.ports.events import EventEmitter

_logger = logging.getLogger(__name__)


def _invalidate_for_clean_scan(
    config: RunConfig, files: list[str], dim_id: str, cache: CacheBackend,
) -> bool:
    """Delete this dim's cache entries before a clean-scan dispatch, so a
    cancelled clean-scan + retry never short-circuits on stale entries
    that pre-date the clean-scan."""
    bypass_reads = not config.options.incremental
    if bypass_reads:
        wiped = 0
        for f in files:
            key = build_cache_key_for_file(config, f, dim_id)
            try:
                cache.delete(key)
                wiped += 1
            except Exception as exc:  # noqa: BLE001
                _logger.debug("[%s] cache delete failed for %s: %s", dim_id, f, exc)
        _logger.info(
            "[%s] cache: invalidated %d entries before clean-scan dispatch",
            dim_id, wiped,
        )
    return bypass_reads


def _classify_and_log(
    config: RunConfig, dim_id: str, files: list[str], cache: CacheBackend,
    bypass_reads: bool,
) -> ClassifyResult:
    """Classify via cache, log the hit/miss split (surfacing provenance
    drift so cross-model/standards reuse is never silent), and emit the
    per-dim cache_stats marker for the dashboard / SSE stream."""
    classify = classify_files_via_cache(
        config, dim_id, files, cache, bypass_reads=bypass_reads,
    )
    n_hits = len(files) - len(classify.misses)
    drift_note = format_provenance_drift(classify.provenance_drift, reused=n_hits)
    _logger.info(
        "[%s] cache: %d hits / %d misses (%d total)%s%s",
        dim_id, n_hits, len(classify.misses), len(files),
        " - clean-scan invalidated" if bypass_reads else "",
        f" - reused {drift_note}" if drift_note else "",
    )
    emit_marker(
        "cache_stats", dimension=dim_id, hits=n_hits, misses=len(classify.misses),
        total=len(files),
        mode="clean-scan-invalidated" if bypass_reads else "incremental",
    )
    return classify


def _handle_all_hits(
    config: RunConfig, dim_id: str, ctx: _AnalysisContext, jsonl: Path,
    classify: ClassifyResult, files: list[str],
    trust_model: TrustModel | None,
    writer_factory: Callable[[Path], EventEmitter] | None,
) -> Evidence | None:
    """All-hits short-circuit: no dispatch needed. Appends (not overwrites)
    since a dim may run multiple times in the same run (e.g. V1's backfill
    phase); dedup after handles overlap from a same-run repeat."""
    from quodeq.analysis.subagents.jsonl_utils import deduplicate_jsonl
    _write_findings(
        jsonl, classify.cached_findings, append=True,
        unconsolidated=classify.unconsolidated_findings,
        trust_model=trust_model, writer_factory=writer_factory,
    )
    if jsonl.exists():
        deduplicate_jsonl(jsonl)
    return parse_evidence_from_jsonl(
        config, dim_id, ctx, jsonl,
        files_read=_compute_files_read(classify, jsonl, files),
    )


def _prepare_miss_dispatch(
    config: RunConfig, dim_id: str, jsonl: Path, classify: ClassifyResult,
    trust_model: TrustModel | None,
    writer_factory: Callable[[Path], EventEmitter] | None,
) -> RunConfig:
    """Build the dispatcher's file-filtered config, pre-write any cached
    findings, and persist the miss-key sidecar the discard path needs."""
    miss_options = replace(config.options, incremental_file_filter=set(classify.misses))
    miss_config = replace(config, options=miss_options)
    if classify.cached_findings or classify.unconsolidated_findings:
        _write_findings(
            jsonl, classify.cached_findings, append=True,
            unconsolidated=classify.unconsolidated_findings,
            trust_model=trust_model, writer_factory=writer_factory,
        )
    sidecar = _evidence_dir(config) / f"{dim_id}_dispatch_keys.json"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps(classify.miss_keys, indent=2), encoding="utf-8")
    return miss_config


def _start_watchers(
    config: RunConfig, dim_id: str, jsonl: Path, classify: ClassifyResult,
    cache: CacheBackend, persist_interval_s: float,
) -> tuple[threading.Event, threading.Thread, FailureStreakWatcher]:
    """Start the periodic-persist watcher (safety net only; on_file_done
    already persists synchronously) and the failure-streak breaker.
    Creates the evidence JSONL up front, when absent, so the breaker's
    first poll doesn't warn about a missing file."""
    def _persist_now() -> None:
        persist_dispatch_results(
            config, dim_id, miss_files=classify.misses,
            jsonl_path=jsonl, miss_keys=classify.miss_keys, cache=cache,
        )

    stop_event = threading.Event()
    watcher = threading.Thread(
        target=_periodic_persist,
        args=(stop_event, _persist_now, persist_interval_s, _logger.warning),
        daemon=True,
        name=f"v2-cache-persist-{dim_id}",
    )
    watcher.start()

    jsonl.parent.mkdir(parents=True, exist_ok=True)
    if not jsonl.exists():
        jsonl.touch()

    breaker = FailureStreakWatcher(
        jsonl,
        threshold=_resolve_failure_streak_threshold(
            config.options, override=failure_streak_override(),
        ),
    )
    breaker.start()
    return stop_event, watcher, breaker


def _handle_breaker_trip(
    config: RunConfig, dim_id: str, ctx: _AnalysisContext, jsonl: Path,
    classify: ClassifyResult, files: list[str],
) -> Evidence:
    """Salvage the completed-so-far JSONL instead of discarding the whole
    dimension, flagging failure_streak. Raises when there is nothing to
    salvage, so the dim is marked INCOMPLETE as before."""
    if jsonl.exists():
        salvaged = parse_evidence_from_jsonl(
            config, dim_id, ctx, jsonl,
            files_read=_compute_files_read(classify, jsonl, files),
        )
        if salvaged is not None and salvaged.principles:
            salvaged.exit_reason = "failure_streak"
            return salvaged
    raise CircuitBreakerError("circuit_breaker")


def _handle_dispatch_result(
    config: RunConfig, dim_id: str, ctx: _AnalysisContext, jsonl: Path,
    classify: ClassifyResult, files: list[str],
    miss_evidence: Evidence | None,
) -> Evidence | None:
    """Finalize Evidence after a normal (non-tripped) dispatch return,
    re-parsing the JSONL so files_read reflects hits + misses."""
    if miss_evidence is None:
        replayed_anything = bool(
            classify.cached_findings or classify.unconsolidated_findings
        )
        if replayed_anything and jsonl.exists():
            return parse_evidence_from_jsonl(
                config, dim_id, ctx, jsonl,
                files_read=_compute_files_read(classify, jsonl, files),
            )
        return None
    return parse_evidence_from_jsonl(
        config, dim_id, ctx, jsonl,
        files_read=_compute_files_read(classify, jsonl, files),
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
    if cache is None:
        cache = LocalFileBackend()
        maybe_collect_legacy_entries(cache.root)
    trust_model = resolve_trust_model(config.src) if config.src is not None else None
    files, _ext, _excluded = _list_source_files(config, dim_id)
    if not files:
        return dispatcher(config, dim_id, idx, ctx, callbacks, log=log)

    bypass_reads = _invalidate_for_clean_scan(config, files, dim_id, cache)
    classify = _classify_and_log(config, dim_id, files, cache, bypass_reads)
    jsonl = _jsonl_path(config, dim_id)
    _write_replayed_keys_sidecar(config, dim_id, classify.unconsolidated_hit_keys)

    if not classify.misses:
        return _handle_all_hits(
            config, dim_id, ctx, jsonl, classify, files, trust_model, writer_factory,
        )

    miss_config = _prepare_miss_dispatch(
        config, dim_id, jsonl, classify, trust_model, writer_factory,
    )
    stop_event, watcher, breaker = _start_watchers(
        config, dim_id, jsonl, classify, cache, persist_interval_s,
    )
    try:
        miss_evidence = dispatcher(miss_config, dim_id, idx, ctx, callbacks, log=log)
    finally:
        # No join timeout (c88be50e regression: a capped join dropped the
        # final persist tick on long dims). Breaker keeps its own 5s cap.
        stop_event.set()
        watcher.join()
        breaker.stop_and_join(timeout=5.0)
    if breaker.trip_event is not None:
        return _handle_breaker_trip(config, dim_id, ctx, jsonl, classify, files)
    return _handle_dispatch_result(
        config, dim_id, ctx, jsonl, classify, files, miss_evidence,
    )
