"""Incremental analysis — top-level orchestrator for a single dimension."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from quodeq.analysis._backfill import BackfillContext, extract_files_from_jsonl, run_backfill_phase
from quodeq.analysis._incremental_evidence import (
    parse_evidence_from_jsonl, save_dimension_fingerprint,
)
from quodeq.analysis.cache.dimension_helpers import classify_files_via_cache
from quodeq.analysis.cache.flags import is_cache_v2_enabled
from quodeq.analysis.cache.local import LocalFileBackend
from quodeq.analysis.incremental import ClassificationInput, classify_files
from quodeq.analysis._incremental_context import IncrementalCoverage
from quodeq.analysis._incremental_phases import (
    _finalize_incremental, _list_all_source_files,
    _maybe_carry_forward, _run_phase1_analysis,
)
from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis.fingerprint import find_previous_fingerprint
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.core.evidence.model import Evidence

_logger = logging.getLogger(__name__)


def _actual_analyzed_files(evidence_dir: "Path", dimension: str) -> set[str]:
    """Return the set of files that were actually analyzed (have evidence).

    Reads from the queue (files taken by agents) and the JSONL (files with
    findings).  This is more accurate than using classification.to_analyze,
    which lists files *queued* for analysis — not files that finished before
    the pool timed out.
    """
    analyzed: set[str] = set()
    queue_path = Path(evidence_dir) / f"{dimension}_queue.json"
    if queue_path.exists():
        try:
            analyzed |= set(FileQueue(queue_path).all_taken_files())
        except (OSError, ValueError, KeyError):
            pass
    analyzed |= extract_files_from_jsonl(Path(evidence_dir) / f"{dimension}_evidence.jsonl")
    return analyzed


def _try_v2_full_hit(
    config: RunConfig, dimension: str, ctx: _AnalysisContext,
) -> Evidence | None:
    """V2 fast-path: if every file is a cache hit, return Evidence directly.

    Returns None when any file misses, so the caller can fall through to
    V1's incremental path (which still uses the per-file V2 wiring inside
    _process_single_dimension for the dispatched subset).

    Also writes a V1-compatible fingerprint so flipping the flag off later
    doesn't trigger a needless full re-analysis.
    """
    files = _list_all_source_files(config, dimension)
    if not files:
        return None

    cache = LocalFileBackend()
    classify = classify_files_via_cache(config, dimension, files, cache)
    if classify.misses:
        return None

    _logger.info(
        "[%s] cache: %d hits / 0 misses (%d total) — V2 fast-path",
        dimension, len(files), len(files),
    )

    evidence_dir = config.work_dir or config.src
    jsonl = evidence_dir / f"{dimension}_evidence.jsonl"
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    with jsonl.open("w", encoding="utf-8") as out:
        for finding in classify.cached_findings:
            out.write(json.dumps(finding) + "\n")

    ev = parse_evidence_from_jsonl(config, dimension, ctx, jsonl, files_read=len(files))
    if ev is None:
        return None

    # Keep V1's fingerprint state consistent so the system can fall back to
    # the V1 path cleanly if the flag is later disabled.
    save_dimension_fingerprint(config, dimension, files=files, analyzed_files=set(files))
    return ev


def run_dimension_incremental(
    config: RunConfig, dimension: str, idx: int, ctx: _AnalysisContext,
) -> Evidence | None:
    """Incremental path: detect changes, carry forward, analyze only changed files."""
    if is_cache_v2_enabled():
        ev = _try_v2_full_hit(config, dimension, ctx)
        if ev is not None:
            return ev

    phase_start = time.monotonic()
    evidence_dir = config.work_dir or config.src

    prev_fp, prev_evidence_dir = find_previous_fingerprint(evidence_dir, dimension)

    files = _list_all_source_files(config, dimension)
    if not files:
        return None

    classification = classify_files(
        inputs=ClassificationInput(
            src=config.src, files=files, prev_fingerprint=prev_fp,
            standards_dir=config.standards_dir, dimension=dimension, language=config.language,
        ),
    )

    _maybe_carry_forward(prev_fp, prev_evidence_dir, classification, dimension, evidence_dir)

    ev = _run_phase1_analysis(config, dimension, idx, ctx, classification)

    prev_analyzed = set(prev_fp.get("analyzed_files", [])) if prev_fp else set()
    # Use actually-analyzed files (queue taken + JSONL evidence), not files
    # queued for analysis — the pool may have timed out before finishing all.
    phase1_actually_analyzed = _actual_analyzed_files(evidence_dir, dimension) - prev_analyzed
    backfill_taken = run_backfill_phase(
        config, dimension, idx, ctx,
        BackfillContext(files=files, prev_analyzed=prev_analyzed, phase1_files=phase1_actually_analyzed,
                        evidence_dir=evidence_dir, phase_start=phase_start),
    )

    all_analyzed = prev_analyzed | phase1_actually_analyzed | backfill_taken
    return _finalize_incremental(
        config, dimension, ctx,
        IncrementalCoverage(
            files=files, all_analyzed=all_analyzed,
            files_read=len(phase1_actually_analyzed) + len(backfill_taken) + len(classification.unchanged),
        ),
    )
