"""Dimension-level cache helpers — bridge between RunConfig + filesystem
and the cache layer.

These are pure functions used by the V2 dimension processor (Phase B5):

  - ``build_cache_key_for_file``: derive a deterministic cache key from
    the current ``RunConfig`` and a target file. The key composition
    matches ``CacheKey``: file content, path, dimension, non-default
    params. Model, prompts, standards and language are provenance, not key.

  - ``classify_files_via_cache``: split a file list into cache hits
    (with findings) and misses (need dispatch). A miss with a real content
    hash first tries adoption from an identical file under another path
    (``_adoption.py``). The miss-key mapping is returned so the caller can
    write entries after dispatch without recomputing keys.

  - ``persist_dispatch_results``: after a dispatch run writes its JSONL,
    group its findings by file and write per-file cache entries for the
    files that were actually dispatched. Empty-finding files get an
    empty entry — a clean analysis is still a hit, not a miss. The
    periodic-persist watcher passes a ``DispatchJsonlState``
    (``_jsonl_state.py``) so each tick reads only appended lines and
    rewrites only the files they touched.

These helpers compose into the canonical V2 dimension processor in
``cache/dimension_runner.py``.

Cache-key composition and provenance-drift tracking live in
``_key_provenance.py`` and are re-exported below for backward compatibility.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from quodeq.analysis._types import RunConfig
from quodeq.analysis.cache._adoption import try_adopt
from quodeq.analysis.cache._jsonl_state import DispatchJsonlState
from quodeq.analysis.cache._key_provenance import (
    _SCHEMA_VERSION,
    _accumulate_drift,
    _current_provenance,
    _hash_prompts_combined,  # noqa: F401 -- re-export
    _model_id_from,
    build_cache_key_for_file,  # noqa: F401 -- re-export
    build_cache_key_struct,
    format_provenance_drift,  # noqa: F401 -- re-export
)
from quodeq.analysis.cache.backend import CacheBackend
from quodeq.analysis.cache.entry import CacheEntry, build_provenance, quodeq_version
from quodeq.analysis.cache.key import compute_key
from quodeq.analysis.fingerprint import _hash_file

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClassifyResult:
    """Result of splitting a file list against the cache."""

    cached_findings: list[dict] = field(default_factory=list)
    misses: list[str] = field(default_factory=list)
    # Per-file cache key for the missed files, so the caller can write
    # entries after dispatch without recomputing the key.
    miss_keys: dict[str, str] = field(default_factory=dict)
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


def _classify_one_file(
    config: RunConfig, dimension: str, f: str, cache: CacheBackend, *, bypass_reads: bool,
    current_prov: dict | None,
) -> tuple[str, CacheEntry | None, dict | None, bool]:
    """Classify one file against the cache. Returns (key, hit, current_prov,
    adopted), where hit is None on a miss, current_prov is lazily computed on
    the first hit (passed through so the caller only pays for it once), and
    adopted says the hit came from ``try_adopt`` rather than a direct get."""
    struct = build_cache_key_struct(config, f, dimension)
    key = compute_key(struct)
    hit = None if bypass_reads else cache.get(key)
    adopted = False
    if hit is None and not bypass_reads:
        hit = try_adopt(cache, struct, key, language=config.language or "")
        adopted = hit is not None
    if hit is not None and current_prov is None:
        current_prov = _current_provenance(config, dimension)
    return key, hit, current_prov, adopted


def _partition_files_by_cache(
    config: RunConfig, dimension: str, files: list[str], cache: CacheBackend,
    *, bypass_reads: bool,
) -> ClassifyResult:
    """Partition ``files`` into cache hits and misses, building a ClassifyResult."""
    cached_findings: list[dict] = []
    misses: list[str] = []
    miss_keys: dict[str, str] = {}
    provenance_drift: dict = {}
    unconsolidated_findings: list[dict] = []
    unconsolidated_hit_keys: dict[str, str] = {}
    adopted = 0
    current_prov: dict | None = None  # computed lazily, only if there are hits
    for f in files:
        key, hit, current_prov, was_adopted = _classify_one_file(
            config, dimension, f, cache, bypass_reads=bypass_reads, current_prov=current_prov,
        )
        if hit is None:
            misses.append(f)
            miss_keys[f] = key
        else:
            adopted += int(was_adopted)
            if hit.consolidated:
                cached_findings.extend(hit.findings)
            else:
                unconsolidated_findings.extend(hit.findings)
                unconsolidated_hit_keys[f] = key
            assert current_prov is not None  # set on the first hit, above
            _accumulate_drift(provenance_drift, hit.provenance or {}, current_prov)
    return ClassifyResult(
        cached_findings=cached_findings,
        misses=misses,
        miss_keys=miss_keys,
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
    ``config._classify_cache`` is set to a dict, this function stashes
    its result there on the first call for a given ``(dimension, files)``
    pair and short-circuits the second call. The stash MUST NOT short-
    circuit when ``bypass_reads`` is True — clean-scan deletes entries
    immediately before this call, so an upfront classify's hits are
    stale by the time the dim runner asks again.
    """
    files_tuple = tuple(files)
    run_cache = config._classify_cache
    if not bypass_reads and run_cache is not None:
        stashed = run_cache.get(dimension)
        if stashed is not None and stashed[0] == files_tuple:
            return stashed[1]

    result = _partition_files_by_cache(config, dimension, files, cache, bypass_reads=bypass_reads)
    if not bypass_reads and run_cache is not None:
        run_cache[dimension] = (files_tuple, result)
    return result


def _group_findings_by_file(jsonl_path: Path) -> tuple[dict[str, list[dict]], set[str]]:
    """Read a JSONL of findings + markers and return (grouped_findings, ok_files).

    One-shot form of ``DispatchJsonlState`` for callers that read a finished
    file once (replay, tests); the watcher keeps one state across ticks.
    Marker lines are recognised by the ``_marker`` key and excluded from the
    grouped findings. ``ok_files`` contains the set of files whose *most
    recent* file_done marker has status='ok'. Files whose latest marker is
    'error' (or have no marker at all) are not in the set.
    """
    state = DispatchJsonlState()
    if not _advance_or_warn(state, jsonl_path, include_tail=True):
        return {}, set()
    return state.grouped, state.ok_files()


def _advance_or_warn(
    state: DispatchJsonlState, jsonl_path: Path, *, include_tail: bool,
) -> bool:
    """Advance *state*; an unreadable JSONL is logged here and yields False."""
    try:
        state.advance(jsonl_path, include_tail=include_tail)
    except OSError as exc:
        _logger.warning("failed to read JSONL %s: %s", jsonl_path, exc)
        return False
    return True


def _build_cache_entry_for_file(
    config: RunConfig, dimension: str, f: str, key: str, grouped: dict[str, list[dict]],
    *, model_id: str, standards_hash: str, prompts_hash: str, effective_params: dict,
    version: str, params_hash: str = "",
) -> CacheEntry:
    """Build the CacheEntry for one dispatched file's persisted result."""
    return CacheEntry(
        key=key,
        schema_version=_SCHEMA_VERSION,
        findings=grouped.get(f, []),
        files_read=1,
        file_path=f,
        dimension=dimension,
        model_id=model_id,
        file_content_hash=_hash_file(config.src / f) or "",
        language=config.language or "",
        params_hash=params_hash,
        provenance=build_provenance(
            model_id=model_id, prompts_hash=prompts_hash,
            standards_hash=standards_hash, version=version,
            effective_params=effective_params,
        ),
        # Born unconsolidated: no completed run has these findings in its
        # report yet. mark_run_consolidated flips it when this run ends done.
        #
        # Accepted race: two concurrent runs on one project can both treat
        # file X as a miss. If run A reaches done and flips X to
        # consolidated, run B's periodic-persist watcher can then rewrite
        # X here with consolidated=False. If B is later cancelled, X reads
        # as unconsolidated even though A already put those findings in a
        # completed Overview, so the next run surfaces them as "new" once.
        # Cosmetic, requires concurrent runs on one project, and
        # self-heals on the next done run. Not fixing.
        consolidated=False,
    )


def persist_dispatch_results(
    config: RunConfig, dimension: str, *, miss_files: list[str],
    jsonl_path: Path, miss_keys: dict[str, str], cache: CacheBackend,
    standards_hash: str, params_hash: str, effective_params: dict,
    prompts_hash: str, state: DispatchJsonlState | None = None,
) -> None:
    """Write per-file cache entries for files with a file_done='ok' marker.

    Files in *miss_files* that lack an ok marker (worker crashed, token-out,
    abandoned) are NOT cached, so the next run re-dispatches them.

    *standards_hash*/*params_hash*/*effective_params*/*prompts_hash* are
    provenance context that's constant for the whole dispatch (same
    standards_dir/prompts_dir/dimension throughout). Callers compute them
    once and pass them in, rather than this function recomputing them on
    every call — this is invoked on a fixed interval by the periodic-persist
    watcher for the life of one dispatch.

    For the same reason the watcher passes one *state* per dispatch: a tick
    then reads only the lines appended since the previous one and rewrites
    only the ok files those lines touched. Without *state* the call is
    one-shot and persists every ok file in the JSONL.
    """
    if not jsonl_path.is_file():
        return
    one_shot = state is None
    if state is None:
        state = DispatchJsonlState()
    if not _advance_or_warn(state, jsonl_path, include_tail=one_shot):
        return
    ok_files = state.ok_files()
    model_id = _model_id_from(config)
    version = quodeq_version()
    for f in miss_files:
        if f not in ok_files or f not in state.dirty:
            continue
        key = miss_keys.get(f)
        if key is None:
            _logger.debug("persist_dispatch_results: no key for %s; skipping", f)
            continue
        entry = _build_cache_entry_for_file(
            config, dimension, f, key, state.grouped,
            model_id=model_id, standards_hash=standards_hash, prompts_hash=prompts_hash,
            effective_params=effective_params, version=version, params_hash=params_hash,
        )
        cache.put(key, entry)
    # Cleared only once every put landed, so a failed tick retries its files.
    state.dirty.clear()
