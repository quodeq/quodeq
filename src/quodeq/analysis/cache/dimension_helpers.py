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
    write entries after dispatch without recomputing keys. Lives in
    ``_classify.py`` with ``ClassifyResult``; re-exported below.

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
from dataclasses import dataclass
from pathlib import Path

from quodeq.analysis.run_types import RunConfig
from quodeq.analysis.cache._classify import (
    ClassifyResult,
    _classify_one_file,  # noqa: F401 -- re-export
    _partition_files_by_cache,  # noqa: F401 -- re-export
    classify_files_via_cache,  # noqa: F401 -- re-export
)
from quodeq.analysis.cache._jsonl_state import DispatchJsonlState
from quodeq.analysis.cache._key_provenance import (
    _SCHEMA_VERSION,
    _content_hash_for,
    _current_provenance,  # noqa: F401 -- re-export
    _hash_prompts_combined,  # noqa: F401 -- re-export
    _model_id_from,
    build_cache_key_for_file,  # noqa: F401 -- re-export
    format_provenance_drift,  # noqa: F401 -- re-export
)
from quodeq.analysis.cache.entry import CacheEntry, build_provenance, quodeq_version

# CachePersistProvenance/CachePersistTarget live in _persist_watcher.py
# (which imports from here); referenced below only as annotations.
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CacheEntryTarget:
    """One dispatched file's persisted-entry identity: file path, cache
    key, and the model/version stamped on every entry in the dispatch."""

    file_path: str
    key: str
    model_id: str
    version: str
    content_hash: str = ""  # classify's hash for this file; "" re-hashes (legacy)
    # The file's ``stat_key`` when classify hashed it. The hash above is
    # reused only while it still matches; None re-hashes. See
    # ``_key_provenance._content_hash_for``.
    content_stamp: tuple[int, int] | None = None


def group_findings_by_file(jsonl_path: Path) -> tuple[dict[str, list[dict]], set[str]]:
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
    config: RunConfig, dimension: str, target: CacheEntryTarget,
    grouped: dict[str, list[dict]], provenance: CachePersistProvenance,
) -> CacheEntry:
    """Build the CacheEntry for one dispatched file's persisted result."""
    content_hash = _content_hash_for(
        config.src / target.file_path, target.content_hash, target.content_stamp,
    )
    if not content_hash:
        _logger.debug("content hash unavailable for %s; cache entry stored without it", target.file_path)
    return CacheEntry(
        key=target.key,
        schema_version=_SCHEMA_VERSION,
        findings=grouped.get(target.file_path, []),
        files_read=1,
        file_path=target.file_path,
        dimension=dimension,
        model_id=target.model_id,
        file_content_hash=content_hash,
        language=config.language or "",
        params_hash=provenance.params_hash,
        provenance=build_provenance(
            model_id=target.model_id, prompts_hash=provenance.prompts_hash,
            standards_hash=provenance.standards_hash, version=target.version,
            effective_params=provenance.effective_params,
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
    config: RunConfig, dimension: str, *, classify: ClassifyResult,
    provenance: CachePersistProvenance, target: CachePersistTarget,
) -> None:
    """Write per-file cache entries for files with a file_done='ok' marker.

    Files in *classify.misses* that lack an ok marker (worker crashed,
    token-out, abandoned) are NOT cached, so the next run re-dispatches them.

    *provenance* is dispatch-constant hash context the caller computes once,
    not on every watcher tick. *target.state* is the watcher's shared
    per-dispatch state: reused across ticks, so a tick reads only the lines
    appended since the previous one. ``target.state is None`` makes the
    call one-shot, re-reading and persisting the whole JSONL.
    """
    if not target.jsonl_path.is_file():
        return
    one_shot = target.state is None
    state = target.state if target.state is not None else DispatchJsonlState()
    if not _advance_or_warn(state, target.jsonl_path, include_tail=one_shot):
        return
    ok_files = state.ok_files()
    model_id = _model_id_from(config)
    version = quodeq_version()
    for f in classify.misses:
        if f not in ok_files or f not in state.dirty:
            continue
        key = classify.miss_keys.get(f)
        if key is None:
            _logger.debug("persist_dispatch_results: no key for %s; skipping", f)
            continue
        entry_target = CacheEntryTarget(
            file_path=f, key=key, model_id=model_id, version=version,
            content_hash=classify.miss_hashes.get(f, ""),
            content_stamp=classify.miss_stamps.get(f),
        )
        entry = _build_cache_entry_for_file(config, dimension, entry_target, state.grouped, provenance)
        target.cache.put(key, entry)
    # A raising put keeps dirty for the next tick. A put that fails silently
    # (LocalFileBackend swallows OSError) is redone by the final full re-read.
    state.dirty.clear()
