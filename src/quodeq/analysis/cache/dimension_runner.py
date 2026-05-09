"""V2 cache-aware dimension processor — composes B4 helpers with the
existing dispatcher boundary.

The flow:

  1. List source files (respecting any incremental_file_filter set by
     the caller)
  2. Classify each file via the cache: hits return findings directly,
     misses go to the dispatcher
  3. All-hits short-circuit: write cached findings to JSONL and parse
     to Evidence without calling the dispatcher
  4. Otherwise: dispatch misses via process_dimension_with_subagents
     with incremental_file_filter restricted to the miss set
  5. Persist new findings to cache (per-file) from the dispatch JSONL
  6. If there were also hits, append cached findings to the JSONL and
     re-parse for the final Evidence

This sits *above* the existing dispatcher — V1's machinery (carry-
forward, fingerprint, queue salvage) still runs for the dispatched
files. That's intentional: the cache supersedes V1's incrementality
decisions but keeps the proven dispatch path intact.

Known limitation: when migrating from a long-lived V1 install to V2,
V1's carry-forward might surface findings for files V2 has cached,
producing duplicates in the dispatch JSONL. The fix is to suppress
V1's carry-forward when V2 is active; B6 cleanup will handle that
once the V1 path is being deleted.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

from quodeq.analysis._evidence_parser import parse_evidence_from_jsonl
from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis.cache.backend import CacheBackend
from quodeq.analysis.cache.dimension_helpers import (
    ClassifyResult,
    classify_files_via_cache,
    persist_dispatch_results,
)
from quodeq.analysis.cache.local import LocalFileBackend
from quodeq.analysis.subagents._source_files import _list_source_files
from quodeq.analysis.subagents.runner import (
    DimensionCallbacks,
    process_dimension_with_subagents,
)
from quodeq.core.evidence.model import Evidence
from quodeq.engine._runner_markers import emit_marker

_logger = logging.getLogger(__name__)

# How often the watcher thread persists in-flight cache entries during
# dispatch. Smaller = less work lost on cancel; larger = less I/O during
# normal runs. 30s is a pragmatic default — at typical model dispatch
# speeds (~10-30s per file), each tick covers a handful of completed files.
_PERSIST_INTERVAL_S = 30.0


def _periodic_persist(
    stop_event: threading.Event, persist_fn: Any,
    interval: float,
) -> None:
    """Background thread: call persist_fn() until stop_event is set.

    Each tick is best-effort — exceptions never propagate to the caller
    and never kill the watcher. Final persist happens on stop signal so
    the watcher's last-known state is also written to cache.
    """
    while not stop_event.wait(timeout=interval):
        try:
            persist_fn()
        except Exception as exc:  # noqa: BLE001 — never kill the dispatch
            _logger.warning("incremental cache persist failed: %s", exc)
    # Final persist after stop signaled (e.g. dispatch finished or raised).
    try:
        persist_fn()
    except Exception as exc:  # noqa: BLE001
        _logger.warning("final cache persist failed: %s", exc)


def _evidence_dir(config: RunConfig) -> Path:
    return config.work_dir or config.src


def _jsonl_path(config: RunConfig, dim_id: str) -> Path:
    return _evidence_dir(config) / f"{dim_id}_evidence.jsonl"


def _write_findings(jsonl: Path, findings: list[dict], *, append: bool) -> None:
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with jsonl.open(mode) as out:
        for finding in findings:
            out.write(json.dumps(finding) + "\n")


def process_dimension_with_cache(
    config: RunConfig, dim_id: str, idx: int, ctx: _AnalysisContext,
    callbacks: DimensionCallbacks,
    *, cache: CacheBackend | None = None,
) -> Evidence | None:
    """V2 entry point — content-addressed cache replaces V1 change detection.

    Falls through to ``process_dimension_with_subagents`` when there's
    no source-file list to classify (matches V1's no-files fallback).
    """
    if cache is None:
        cache = LocalFileBackend()

    files, _ext = _list_source_files(config, dim_id)
    if not files:
        # Nothing to classify — defer to existing path so the no-files
        # warning + single-agent fallback runs unchanged.
        return process_dimension_with_subagents(config, dim_id, idx, ctx, callbacks)

    # Clean-scan (incremental=False) bypasses cache reads — fresh dispatch
    # every time — but writes still happen below so the cache stays current.
    bypass_reads = not config.options.incremental
    classify = classify_files_via_cache(
        config, dim_id, files, cache, bypass_reads=bypass_reads,
    )
    n_hits = len(files) - len(classify.misses)
    _logger.info(
        "[%s] cache: %d hits / %d misses (%d total)%s",
        dim_id, n_hits, len(classify.misses), len(files),
        " — clean-scan refresh" if bypass_reads else "",
    )
    # Structured marker for the dashboard / SSE stream — one event per
    # dim summarising hit/miss split. Per-file events would be too noisy
    # for a UI-level stream; per-dim is the right granularity.
    emit_marker(
        "cache_stats",
        dimension=dim_id,
        hits=n_hits,
        misses=len(classify.misses),
        total=len(files),
        mode="clean-scan-refresh" if bypass_reads else "incremental",
    )

    jsonl = _jsonl_path(config, dim_id)

    # All-hits short-circuit: no dispatch needed.
    # We append (not overwrite) because callers may invoke us multiple times
    # within the same dim (e.g. V1's backfill phase under stacked migration).
    # Truncating here would destroy findings written by prior phases.
    # Dedup runs after to handle any overlap from a same-run repeat.
    if not classify.misses:
        from quodeq.analysis.subagents.jsonl_utils import deduplicate_jsonl
        _write_findings(jsonl, classify.cached_findings, append=True)
        if jsonl.exists():
            deduplicate_jsonl(jsonl)
        return parse_evidence_from_jsonl(
            config, dim_id, ctx, jsonl, files_read=len(files),
        )

    # Dispatch misses via the existing path, with file filter restricted
    # to the miss set so the pool only processes uncached files.
    miss_options = replace(config.options, incremental_file_filter=set(classify.misses))
    miss_config = replace(config, options=miss_options)

    # Periodic persist watcher: persists what's in JSONL every
    # _PERSIST_INTERVAL_S seconds. If the dispatch is cancelled (SIGTERM,
    # exception, etc.) the cache retains the work that completed before
    # the cancel — instead of losing the entire dim's progress.
    def _persist_now() -> None:
        persist_dispatch_results(
            config, dim_id, miss_files=classify.misses,
            jsonl_path=jsonl, miss_keys=classify.miss_keys, cache=cache,
        )

    stop_event = threading.Event()
    watcher = threading.Thread(
        target=_periodic_persist,
        args=(stop_event, _persist_now, _PERSIST_INTERVAL_S),
        daemon=True,
        name=f"v2-cache-persist-{dim_id}",
    )
    watcher.start()

    try:
        miss_evidence = process_dimension_with_subagents(
            miss_config, dim_id, idx, ctx, callbacks,
        )
    finally:
        # Signal the watcher to do a final persist and exit. Whatever
        # completed before this point gets cached, whether the dispatch
        # returned cleanly or raised.
        stop_event.set()
        watcher.join(timeout=5.0)

    if miss_evidence is None:
        # Dispatch returned None — final persist already ran via the
        # watcher, so any partial completion is preserved.
        return None

    # If there are also cache hits, merge them into the JSONL and
    # re-parse so the returned Evidence reflects the full picture.
    # Dedup handles overlap with anything earlier phases may have written.
    if classify.cached_findings:
        from quodeq.analysis.subagents.jsonl_utils import deduplicate_jsonl
        _write_findings(jsonl, classify.cached_findings, append=True)
        if jsonl.exists():
            deduplicate_jsonl(jsonl)
        return parse_evidence_from_jsonl(
            config, dim_id, ctx, jsonl, files_read=len(files),
        )

    return miss_evidence
