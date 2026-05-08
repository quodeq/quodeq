"""Dimension-level cache helpers — bridge between RunConfig + filesystem
and the cache layer.

These are pure functions used by the V2 dimension processor (Phase B5):

  - ``build_cache_key_for_file``: derive a deterministic cache key from
    the current ``RunConfig`` and a target file. The key composition
    matches ``CacheKey``: file content, dimension, standards, prompts,
    model, language. Sampling params are not yet plumbed through
    ``AnalysisOptions``; once they are, add them to the key.

  - ``classify_files_via_cache``: split a file list into cache hits
    (with findings) and misses (need dispatch). The miss-key mapping is
    returned so the caller can write entries after dispatch without
    recomputing keys.

  - ``persist_dispatch_results``: after a dispatch run writes its JSONL,
    group its findings by file and write per-file cache entries for the
    files that were actually dispatched. Empty-finding files get an
    empty entry — a clean analysis is still a hit, not a miss.

These helpers do not call into the live pipeline. The Phase B5 wrapper
will compose them with ``process_dimension_with_subagents`` behind the
``QUODEQ_CACHE_V2`` flag.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from quodeq.analysis._types import RunConfig
from quodeq.analysis.cache.backend import CacheBackend
from quodeq.analysis.cache.entry import CacheEntry
from quodeq.analysis.cache.key import CacheKey, compute_key
from quodeq.analysis.fingerprint import _hash_file, _hash_prompts_map, _hash_standards

_logger = logging.getLogger(__name__)

# Bumped on any breaking change to key composition or entry format.
_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ClassifyResult:
    """Result of splitting a file list against the cache."""

    cached_findings: list[dict] = field(default_factory=list)
    misses: list[str] = field(default_factory=list)
    # Per-file cache key for the missed files, so the caller can write
    # entries after dispatch without recomputing the key.
    miss_keys: dict[str, str] = field(default_factory=dict)


def _hash_prompts_combined() -> str:
    """Hash all rules-bearing prompts into a single SHA-256.

    The fingerprint module stores a per-file map for selective
    invalidation; here we collapse it to one string so the cache key
    stays simple. Any prompt change still invalidates correctly.
    """
    pmap = _hash_prompts_map() or {}
    if not pmap:
        return ""
    h = hashlib.sha256()
    for name in sorted(pmap):
        h.update(name.encode())
        h.update(pmap[name].encode())
    return h.hexdigest()


def _model_id_from(config: RunConfig) -> str:
    """Pick the most specific model identifier available."""
    opts = config.options
    return opts.subagent_model or opts.ai_model or "unknown"


def build_cache_key_for_file(config: RunConfig, file_path: str, dimension: str) -> str:
    """Compute the cache key for a (file, dimension) pair under ``config``.

    Returns a 64-char hex SHA-256. Same inputs always produce the same key.
    """
    content_hash = _hash_file(config.src / file_path) or ""
    standards_hash = (
        _hash_standards(config.standards_dir, dimension)
        if config.standards_dir else ""
    ) or ""
    key = CacheKey(
        schema_version=_SCHEMA_VERSION,
        file_content_hash=content_hash,
        file_path=file_path,
        dimension=dimension,
        standards_hash=standards_hash,
        prompts_hash=_hash_prompts_combined(),
        evaluator_hash="",  # not yet versioned; revisit when evaluators are.
        model_id=_model_id_from(config),
        language=config.language or "",
    )
    return compute_key(key)


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
    """
    cached_findings: list[dict] = []
    misses: list[str] = []
    miss_keys: dict[str, str] = {}
    for f in files:
        key = build_cache_key_for_file(config, f, dimension)
        hit = None if bypass_reads else cache.get(key)
        if hit is None:
            misses.append(f)
            miss_keys[f] = key
        else:
            cached_findings.extend(hit.findings)
    return ClassifyResult(
        cached_findings=cached_findings,
        misses=misses,
        miss_keys=miss_keys,
    )


def _group_findings_by_file(jsonl_path: Path) -> dict[str, list[dict]]:
    """Read a JSONL of findings and group lines by their ``file`` field."""
    grouped: dict[str, list[dict]] = {}
    if not jsonl_path.is_file():
        return grouped
    try:
        text = jsonl_path.read_text(encoding="utf-8")
    except OSError as exc:
        _logger.warning("failed to read JSONL %s: %s", jsonl_path, exc)
        return grouped
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        f = entry.get("file")
        if isinstance(f, str) and f:
            grouped.setdefault(f, []).append(entry)
    return grouped


def persist_dispatch_results(
    config: RunConfig, dimension: str, *, miss_files: list[str],
    jsonl_path: Path, miss_keys: dict[str, str], cache: CacheBackend,
) -> None:
    """Write per-file cache entries from a dispatch run's JSONL output.

    A successful dispatch that produced no findings for a given file
    still writes an empty entry — the next run hits instead of
    re-dispatching. If the JSONL doesn't exist (dispatch crashed before
    writing), no entries are written: we don't fabricate "no findings"
    when there's no evidence the analysis ran.
    """
    if not jsonl_path.is_file():
        # Dispatch failed before writing; let the next run retry.
        return
    grouped = _group_findings_by_file(jsonl_path)
    model_id = _model_id_from(config)
    for f in miss_files:
        key = miss_keys.get(f)
        if key is None:
            # Caller error: missed file with no key. Skip rather than fabricate.
            _logger.debug("persist_dispatch_results: no key for %s; skipping", f)
            continue
        entry = CacheEntry(
            key=key,
            schema_version=_SCHEMA_VERSION,
            findings=grouped.get(f, []),
            files_read=1,
            file_path=f,
            dimension=dimension,
            model_id=model_id,
        )
        cache.put(key, entry)
