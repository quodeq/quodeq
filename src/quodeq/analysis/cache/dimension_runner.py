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
    _group_findings_by_file,
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


def _compute_files_read(
    classify: ClassifyResult, jsonl_path: Path, all_files: list[str],
) -> int:
    """Return the count of source files reproducible from the cache after
    this run ends.

    A source file is "reproducible" if either:
      - it was a cache hit (``classify.cached_findings`` already carried it
        forward — its cache entry already exists), or
      - it was dispatched and the worker emitted ``file_done="ok"``
        (which triggers a synchronous cache write via
        ``build_cache_writer``, or the watcher's next persist tick).

    Files with ``file_done="error"`` or no marker at all are NOT counted:
    their analysis was incomplete and the cache contains no entry for
    them, so the next run must re-dispatch.

    Pre-fix, ``files_read`` was set to ``len(input_files)`` at every
    callsite, making coverage % (computed downstream as
    ``files_read / source_file_count``) meaningless: it always read 100%
    even on deadline-truncated runs. The user reported a flexibility
    score of "6.6/Adequate" on a run that actually analyzed ~850/3037
    files — the dashboard couldn't tell it was partial.
    """
    n_hits = len(all_files) - len(classify.misses)
    if not jsonl_path.is_file():
        return n_hits
    _grouped, ok_files = _group_findings_by_file(jsonl_path)
    miss_set = set(classify.misses)
    n_dispatch_ok = len(ok_files & miss_set)
    return n_hits + n_dispatch_ok


def _events_log_path(jsonl: Path) -> Path:
    """Return the run's events.jsonl path given a per-dim evidence JSONL.

    Evidence files live at ``<run_dir>/evidence/<dim>_evidence.jsonl``; the
    event log lives at ``<run_dir>/events.jsonl``. Centralising the join so
    the two callers below can't drift apart.
    """
    return jsonl.parent.parent / "events.jsonl"


def _emit_cached_findings(events_log: Path, findings: list[dict]) -> None:
    """Emit cached findings as JUDGMENT_CREATED events to the run's event log.

    Cached findings replayed by the V2 cache in incremental runs were
    landing only in the per-dim JSONL and never reaching ``events.jsonl``.
    The SQL projection runs off ``events.jsonl``, so the dashboard's grade
    tables saw only the freshly-dispatched findings and produced scores
    that disagreed with the CLI's JSON file (e.g. flexibility scoring 9.0
    in the UI vs 7.7 from the CLI on the same run). Mirroring each cached
    finding into the event log closes that gap.

    Exceptions are caught per finding and logged — the JSONL write
    already succeeded above, so an event-emit failure should not propagate
    and roll back the cache restore.
    """
    if not findings:
        return
    from quodeq.core.events.models import JudgmentCreatedEvent  # noqa: PLC0415
    from quodeq.core.events.writer import EventLogWriter  # noqa: PLC0415
    from quodeq.core.finding_mappings import wire_dict_to_judgment  # noqa: PLC0415

    writer = EventLogWriter(events_log)
    for finding in findings:
        try:
            payload = wire_dict_to_judgment(finding)
            writer.emit(JudgmentCreatedEvent(payload=payload))
        except Exception:  # noqa: BLE001 — event-log emit must never break a cache replay
            _logger.warning(
                "cache replay: event emit failed for finding p=%r file=%r line=%r",
                finding.get("p"), finding.get("file"), finding.get("line"),
                exc_info=True,
            )


def _write_findings(
    jsonl: Path, findings: list[dict], *, append: bool,
    emit_events: bool = True,
) -> None:
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with jsonl.open(mode) as out:
        for finding in findings:
            out.write(json.dumps(finding) + "\n")
    if emit_events:
        _emit_cached_findings(_events_log_path(jsonl), findings)


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
            config, dim_id, ctx, jsonl,
            files_read=_compute_files_read(classify, jsonl, files),
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
        #
        # No join timeout: the prior 5s cap was the c88be50e regression
        # that dropped the final persist tick when it ran longer than 5s.
        # On a 790-file flexibility run the user lost ~16% of the cache
        # entries (790 file_done="ok" markers in the JSONL, only 662
        # entries persisted) because the final tick was scanning the whole
        # JSONL and rewriting per-file entries — each persist_dispatch_results
        # call does O(n_files) work and an interrupted final tick silently
        # abandoned every entry it hadn't yet written.
        #
        # The breaker join keeps its 5s cap: it's a separate thread with
        # independent lifecycle whose final tick is bounded I/O.
        stop_event.set()
        watcher.join()
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
                config, dim_id, ctx, jsonl,
                files_read=_compute_files_read(classify, jsonl, files),
            )
        return None

    # Re-parse the JSONL so files_read reflects the total (hits + misses),
    # not just len(misses) which is what the dispatcher's Evidence carries.
    # The dispatcher already deduped on its way out, so no extra dedup here.
    return parse_evidence_from_jsonl(
        config, dim_id, ctx, jsonl,
        files_read=_compute_files_read(classify, jsonl, files),
    )
