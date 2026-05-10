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
import os
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

from quodeq.analysis._evidence_parser import parse_evidence_from_jsonl
from quodeq.analysis._types import AnalysisOptions, RunConfig, _AnalysisContext
from quodeq.analysis.cache.backend import CacheBackend
from quodeq.analysis.cache._failure_streak import (
    CircuitBreakerError,
    FailureStreakWatcher,
)
from quodeq.analysis.cache.dimension_helpers import (
    ClassifyResult,
    build_cache_key_for_file,
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


def _resolve_failure_streak_threshold(opts: AnalysisOptions) -> int:
    """Return the effective breaker threshold.

    Priority: ``QUODEQ_FAILURE_STREAK`` env var > options field. Negative or
    non-integer env values fall back to the options field. 0 disables.
    """
    raw = os.environ.get("QUODEQ_FAILURE_STREAK")
    if raw is not None:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return max(0, opts.failure_streak_threshold)


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

    # Clean-scan (incremental=False) means "I want fresh analysis." The user's
    # mental model: cancelled clean-scan + retry should NOT short-circuit on
    # stale entries that pre-date the clean-scan. So at clean-scan start, we
    # delete the cache entries for this (dim, files) tuple BEFORE classify.
    # If the run completes, the cache is naturally repopulated. If the run
    # cancels mid-flight, the cache only contains what THIS run completed --
    # never ghosts from before. Without this, "clean" only meant "bypass
    # reads," and a cancelled clean run left the prior cache fully intact.
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
    classify = classify_files_via_cache(
        config, dim_id, files, cache, bypass_reads=bypass_reads,
    )
    n_hits = len(files) - len(classify.misses)
    _logger.info(
        "[%s] cache: %d hits / %d misses (%d total)%s",
        dim_id, n_hits, len(classify.misses), len(files),
        " - clean-scan invalidated" if bypass_reads else "",
    )
    # Structured marker for the dashboard / SSE stream - one event per
    # dim summarising hit/miss split. Per-file events would be too noisy
    # for a UI-level stream; per-dim is the right granularity.
    emit_marker(
        "cache_stats",
        dimension=dim_id,
        hits=n_hits,
        misses=len(classify.misses),
        total=len(files),
        mode="clean-scan-invalidated" if bypass_reads else "incremental",
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

    # Pre-write cached findings to the JSONL BEFORE dispatch. Two reasons:
    # (1) Ordering: carries (prior runs' findings) appear first in the JSONL,
    #     fresh dispatch findings appear after. The final report reads
    #     foundation-then-new instead of "new findings, oh by the way here
    #     are the carries tacked on at the end."
    # (2) Single dedup pass: the dispatcher's internal dedup at the end of
    #     its evidence collector runs on the merged JSONL, so the user sees
    #     ONE final "Deduplicated ...: N unique findings" log line. Pre-fix
    #     the user saw two confusing counts -- "27 unique" (dispatch only)
    #     followed by "55 unique" (after we appended cached findings).
    if classify.cached_findings:
        _write_findings(jsonl, classify.cached_findings, append=True)

    # Persist the per-file cache keys to a sidecar so the discard path can
    # locate this dim's V2 cache entries even after the process exits. Without
    # this, a user clicking "discard partial findings" can't wipe entries that
    # were written by the periodic-persist watcher above.
    sidecar = _evidence_dir(config) / f"{dim_id}_dispatch_keys.json"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps(classify.miss_keys, indent=2), encoding="utf-8")

    # Periodic persist watcher: persists what's in JSONL every
    # _PERSIST_INTERVAL_S seconds. If the dispatch is cancelled (SIGTERM,
    # exception, etc.) the cache retains the work that completed before
    # the cancel - instead of losing the entire dim's progress.
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

    breaker = FailureStreakWatcher(
        jsonl, threshold=_resolve_failure_streak_threshold(config.options),
    )
    breaker.start()

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
        breaker.stop_and_join(timeout=5.0)

    if breaker.trip_event is not None:
        # The breaker tripped. Surface a typed exception so the pipeline
        # layer can mark this dim's state with reason=circuit_breaker and
        # the lifecycle layer can record exit_reason=failure_streak.
        raise CircuitBreakerError("circuit_breaker")

    if miss_evidence is None:
        # Dispatch returned None - final persist already ran via the
        # watcher, so any partial completion is preserved. If we have
        # cached findings already in the JSONL (pre-written above), parse
        # them so the run still has SOMETHING to score; otherwise None.
        if classify.cached_findings and jsonl.exists():
            return parse_evidence_from_jsonl(
                config, dim_id, ctx, jsonl, files_read=len(files),
            )
        return None

    # Re-parse the JSONL so files_read reflects the total (hits + misses),
    # not just len(misses) which is what the dispatcher's Evidence carries.
    # The dispatcher already deduped on its way out, so no extra dedup here.
    return parse_evidence_from_jsonl(
        config, dim_id, ctx, jsonl, files_read=len(files),
    )
