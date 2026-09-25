"""Pre-dispatch setup for the V2 cache-aware dimension processor.

``prepare_cache_context`` resolves everything ``dimension_runner``'s
``process_dimension_with_cache`` needs before it decides between the
all-hits short-circuit and a miss dispatch: the cache backend, the trust
model, the source-file list, the hit/miss classification and the evidence
JSONL path. It returns ``None`` for the no-source-files case so the
orchestrator can fall through to the V1 dispatcher.

This module is a leaf of ``dimension_runner``: it must never import back
from it. ``emit_marker`` is used here rather than there, so tests that
intercept the ``cache_stats`` marker patch
``quodeq.analysis.cache._dimension_context.emit_marker`` -- ``mock.patch``
resolves where a name is used. Logging goes through an injected ``log:
LogSink`` instead (core has no stdlib logging); ``dimension_runner.py``
threads through ``opts.callbacks.log``, the same sink the dispatcher uses.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quodeq.analysis.runner_markers import emit_marker
from quodeq.analysis.run_types import RunConfig
from quodeq.analysis.cache._replay import dim_jsonl_path, write_replayed_keys_sidecar
from quodeq.analysis.cache.backend import CacheBackend
from quodeq.analysis.cache.dimension_helpers import (
    ClassifyResult,
    classify_files_via_cache,
    format_provenance_drift,
)
from quodeq.analysis.cache.gc import ensure_cache_ready
from quodeq.analysis.cache.local import LocalFileBackend
from quodeq.analysis.subagents.source_files import list_source_files
from quodeq.context.trust_model import TrustModel, resolve_trust_model
from quodeq.core.observability import NULL_LOG, LogSink


@dataclass(frozen=True)
class CacheContext:
    """Everything resolved once per dimension before dispatch, so the
    orchestrator and its steps pass one object instead of five values.
    """

    cache: CacheBackend
    trust_model: TrustModel | None
    files: list[str]
    classify: ClassifyResult
    jsonl: Path


def _invalidate_for_clean_scan(
    dim_id: str, classify: ClassifyResult, cache: CacheBackend, *, log: LogSink,
) -> None:
    """Delete this dim's cache entries before a clean-scan dispatch, so a
    cancelled clean-scan + retry never short-circuits on stale entries
    that pre-date the clean-scan.

    Runs after classify: with reads bypassed, classify reads nothing from the
    cache and returns every file's key in ``miss_keys``, so each file is
    hashed once and the entries go in one batch.
    """
    wiped = cache.delete_many(list(classify.miss_keys.values()))
    log.info(f"[{dim_id}] cache: invalidated {wiped} entries before clean-scan dispatch")


def _classify_and_log(
    config: RunConfig, dim_id: str, files: list[str], cache: CacheBackend,
    bypass_reads: bool, *, log: LogSink,
) -> ClassifyResult:
    """Classify via cache, log the hit/miss split (surfacing provenance
    drift so cross-model/standards reuse is never silent), and emit the
    per-dim cache_stats marker for the dashboard / SSE stream."""
    classify = classify_files_via_cache(
        config, dim_id, files, cache, bypass_reads=bypass_reads,
    )
    n_hits = len(files) - len(classify.misses)
    drift_note = format_provenance_drift(classify.provenance_drift, reused=n_hits)
    adopted_note = f" - {classify.adopted} adopted from moved files" if classify.adopted else ""
    log.info(
        f"[{dim_id}] cache: {n_hits} hits / {len(classify.misses)} misses "
        f"({len(files)} total)"
        + (" - clean-scan invalidated" if bypass_reads else "")
        + (f" - reused {drift_note}" if drift_note else "")
        + adopted_note
    )
    emit_marker(
        "cache_stats", dimension=dim_id, hits=n_hits, misses=len(classify.misses),
        total=len(files), adopted=classify.adopted,
        mode="clean-scan-invalidated" if bypass_reads else "incremental",
    )
    return classify


def prepare_cache_context(
    config: RunConfig, dim_id: str, cache: CacheBackend | None, *, log: LogSink = NULL_LOG,
) -> CacheContext | None:
    """Resolve the per-dimension cache inputs, or None when there is no
    source-file list to classify (matches V1's no-files fallback)."""
    if cache is None:
        cache = LocalFileBackend()
        ensure_cache_ready(cache.root)
    trust_model = resolve_trust_model(config.src) if config.src is not None else None
    files, _ext, _excluded = list_source_files(config, dim_id)
    if not files:
        return None

    bypass_reads = not config.options.incremental
    classify = _classify_and_log(config, dim_id, files, cache, bypass_reads, log=log)
    if bypass_reads:
        _invalidate_for_clean_scan(dim_id, classify, cache, log=log)
    jsonl = dim_jsonl_path(config, dim_id)
    write_replayed_keys_sidecar(config, dim_id, classify.unconsolidated_hit_keys)
    return CacheContext(cache, trust_model, files, classify, jsonl)
