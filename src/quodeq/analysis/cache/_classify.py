"""Splitting a dimension's file list against the cache.

Split out of ``dimension_helpers.py`` (at the file-length ratchet) along the
seam its own module docstring already draws: this module owns the classify
half -- ``ClassifyResult`` and ``classify_files_via_cache`` -- while
``dimension_helpers`` keeps the persist half and re-exports both names, so
every existing import path still works. Moved verbatim apart from the
per-miss stat stamp (finding 3).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from quodeq.analysis.run_types import ClassifyStash, RunConfig
from quodeq.analysis.cache._adoption import try_adopt
from quodeq.analysis.cache._key_provenance import (
    accumulate_drift,
    current_provenance,
    build_cache_key_struct,
)
from quodeq.analysis.cache.backend import CacheBackend
from quodeq.analysis.cache.entry import CacheEntry
from quodeq.analysis.cache.key import compute_key
from quodeq.analysis.fingerprint import stat_key


@dataclass(frozen=True)
class ClassifyResult:
    """Result of splitting a file list against the cache."""

    cached_findings: list[dict] = field(default_factory=list)
    misses: list[str] = field(default_factory=list)
    # Per-file cache key for the missed files, so the caller can write
    # entries after dispatch without recomputing the key.
    miss_keys: dict[str, str] = field(default_factory=dict)
    miss_hashes: dict[str, str] = field(default_factory=dict)  # per-miss content hash, for the cache writer
    # Per-miss ``stat_key`` read just before that hash, so a write path can
    # tell whether the file is still the one classify hashed.
    miss_stamps: dict[str, tuple[int, int]] = field(default_factory=dict)
    # Per-field drift among cache hits: field -> {"count", "from", "to"}.
    # Only fields that actually drifted appear. Lets the caller surface how
    # many reused findings predate the current model / standards / prompts,
    # so reuse across those boundaries is never silent.
    provenance_drift: dict = field(default_factory=dict)
    # Hits from entries no COMPLETED run has consolidated yet: the producing
    # run was cancelled with "keep findings", failed, or was killed, so the
    # user was never shown these findings in an Overview. Kept apart from
    # cached_findings so the replay path leaves them unstamped and the live
    # feed shows them as this scan's own.
    unconsolidated_findings: list[dict] = field(default_factory=list)
    # file -> cache key for those same entries, so a run that reaches done
    # can flip them to consolidated.
    unconsolidated_hit_keys: dict[str, str] = field(default_factory=dict)
    # Hits served by adopting an entry with identical content from another
    # path (a directory move). Counted so the cache log line and the
    # cache_stats marker can surface the reuse.
    adopted: int = 0


def classify_one_file(
    config: RunConfig, dimension: str, f: str, cache: CacheBackend, *, bypass_reads: bool,
) -> tuple[str, str, CacheEntry | None, bool]:
    """Classify one file against the cache. Returns (key, content_hash, hit,
    adopted); ``adopted`` marks a ``try_adopt`` hit."""
    struct = build_cache_key_struct(config, f, dimension)
    key = compute_key(struct)
    hit = None if bypass_reads else cache.get(key)
    adopted = False
    if hit is None and not bypass_reads:
        hit = try_adopt(cache, struct, key, language=config.language or "")
        adopted = hit is not None
    return key, struct.file_content_hash, hit, adopted


def count_cache_misses(
    config: RunConfig, dimension: str, files: list[str], cache: CacheBackend,
) -> int:
    """How many of ``files`` would miss the cache, without reading any entry.

    Same keys and adoption as :func:`classify_one_file`, but a hit is only an
    existence check. For callers that need the count, not the findings (the
    /estimates endpoint). A corrupt entry, which ``get`` treats as a miss,
    counts as a hit here.
    """
    misses = 0
    for f in files:
        struct = build_cache_key_struct(config, f, dimension)
        key = compute_key(struct)
        if cache.has(key):
            continue
        if try_adopt(cache, struct, key, language=config.language or "") is None:
            misses += 1
    return misses


def partition_files_by_cache(
    config: RunConfig, dimension: str, files: list[str], cache: CacheBackend,
    *, bypass_reads: bool,
) -> ClassifyResult:
    """Partition ``files`` into cache hits and misses, building a ClassifyResult."""
    cached_findings: list[dict] = []
    misses: list[str] = []
    miss_keys: dict[str, str] = {}
    miss_hashes: dict[str, str] = {}
    miss_stamps: dict[str, tuple[int, int]] = {}
    provenance_drift: dict = {}
    unconsolidated_findings: list[dict] = []
    unconsolidated_hit_keys: dict[str, str] = {}
    adopted = 0
    current_prov: dict | None = None  # computed lazily, only if there are hits
    for f in files:
        # Stamped before the hash below, never after: a file that changes
        # between the two then carries a stamp older than its hash, and the
        # write path re-hashes rather than trusting a stale hash.
        stamp = stat_key(config.src / f)
        key, content_hash, hit, was_adopted = classify_one_file(
            config, dimension, f, cache, bypass_reads=bypass_reads,
        )
        if hit is None:
            misses.append(f)
            miss_keys[f], miss_hashes[f] = key, content_hash
            if stamp is not None:
                miss_stamps[f] = stamp
        else:
            if current_prov is None:
                current_prov = current_provenance(config, dimension)
            adopted += int(was_adopted)
            if hit.consolidated:
                cached_findings.extend(hit.findings)
            else:
                unconsolidated_findings.extend(hit.findings)
                unconsolidated_hit_keys[f] = key
            assert current_prov is not None  # set on the first hit, above
            accumulate_drift(provenance_drift, hit.provenance or {}, current_prov)
    return ClassifyResult(
        cached_findings=cached_findings,
        misses=misses,
        miss_keys=miss_keys, miss_hashes=miss_hashes, miss_stamps=miss_stamps,
        provenance_drift=provenance_drift,
        unconsolidated_findings=unconsolidated_findings,
        unconsolidated_hit_keys=unconsolidated_hit_keys,
        adopted=adopted,
    )


def classify_files_via_cache(
    config: RunConfig, dimension: str, files: list[str],
    cache: CacheBackend,
    *, bypass_reads: bool = False,
) -> ClassifyResult:
    """Split ``files`` into cache hits (findings) and misses (need dispatch).

    When ``bypass_reads`` is True (e.g. honoring ``--clean-scan``), every
    file is forced into the misses bucket regardless of cache state. The
    miss_keys map is still populated so callers can write fresh entries
    after dispatch — clean-scan refreshes the cache rather than ignoring it.

    The pipeline classifies twice per dim (estimates + dim runner). When
    ``config.classify_stash`` is set to a dict, this function stashes
    its result there on the first call for a given ``(dimension, files)``
    pair and short-circuits the second call. The stash MUST NOT short-
    circuit when ``bypass_reads`` is True — clean-scan deletes entries
    after this call, so an upfront classify's hits are stale by the
    time the dim runner asks again.
    """
    files_tuple = tuple(files)
    run_cache = config.classify_stash
    if not bypass_reads and run_cache is not None:
        stashed = run_cache.get(dimension)
        if stashed is not None and stashed.files == files_tuple:
            return stashed.result

    result = partition_files_by_cache(config, dimension, files, cache, bypass_reads=bypass_reads)
    if not bypass_reads and run_cache is not None:
        run_cache[dimension] = ClassifyStash(files_tuple, result)
    return result
