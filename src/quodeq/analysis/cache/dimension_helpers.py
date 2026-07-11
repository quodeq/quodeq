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

These helpers compose into the canonical V2 dimension processor in
``cache/dimension_runner.py``.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from quodeq.analysis._types import RunConfig
from quodeq.analysis.cache.backend import CacheBackend
from quodeq.analysis.cache.entry import CacheEntry, build_provenance, quodeq_version
from quodeq.analysis.cache.key import CacheKey, compute_key
from quodeq.analysis.fingerprint import _hash_file, _hash_prompts_map, _hash_standards

_logger = logging.getLogger(__name__)

# Bumped on any breaking change to key composition or entry format.
# v1 -> v2: file_done marker contract; entries written without marker
# filtering are no longer trusted, so old entries naturally invalidate
# on the next input change.
# v2 -> v3: permissive key — model/prompts/standards/sampling left the key
# (now provenance on the entry). The formula change re-keys every entry, so
# schema-2 entries land in a different namespace that schema-3 lookups never
# reach; the one-time GC (cache/gc.py) then reclaims them. This is the LAST
# key change that costs a re-eval: entries are now self-describing
# (file_content_hash stored), so any future key change is losslessly
# migratable.
_SCHEMA_VERSION = 3


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


# Provenance fields compared at classify time, in display order.
_PROV_FIELDS = ("model_id", "standards_hash", "prompts_hash", "quodeq_version")
# Fields whose values are human-readable enough to show in a summary; hashes
# are not (an opaque SHA helps no one).
_PROV_HUMAN_VALUE = frozenset({"model_id", "quodeq_version"})
_PROV_LABELS = {
    "model_id": "model",
    "standards_hash": "standards",
    "prompts_hash": "prompts",
    "quodeq_version": "quodeq version",
}


def _current_provenance(config: RunConfig, dimension: str) -> dict:
    """The provenance the current run would stamp on a fresh entry."""
    standards_hash = (
        _hash_standards(config.standards_dir, dimension, config.src)
        if config.standards_dir else ""
    ) or ""
    return {
        "model_id": _model_id_from(config),
        "standards_hash": standards_hash,
        "prompts_hash": _hash_prompts_combined(),
        "quodeq_version": quodeq_version(),
    }


def _accumulate_drift(drift: dict, entry_provenance: dict, current: dict) -> None:
    """Count, per provenance field, hits whose recorded value differs from the
    current run. Unknown (blank/missing) entry values are skipped — we only
    claim drift we can prove, so legacy/empty-provenance entries are quiet."""
    for fname in _PROV_FIELDS:
        old = entry_provenance.get(fname)
        if not old:
            continue
        new = current.get(fname, "")
        if old != new:
            record = drift.setdefault(fname, {"count": 0, "from": old, "to": new})
            record["count"] += 1


def format_provenance_drift(drift: dict, *, reused: int) -> str:
    """One-line summary of how many reused findings predate the current
    model / standards / prompts. Empty string when nothing drifted."""
    if not drift or reused <= 0:
        return ""
    parts: list[str] = []
    for fname in _PROV_FIELDS:
        record = drift.get(fname)
        if not record:
            continue
        label = _PROV_LABELS[fname]
        if fname in _PROV_HUMAN_VALUE:
            parts.append(
                f"{record['count']} across {label} change "
                f"({record['from']} -> {record['to']})"
            )
        else:
            parts.append(f"{record['count']} across {label} change")
    return ", ".join(parts)


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

    Returns a 64-char hex SHA-256. The key is permissive: it depends only on
    the real per-unit inputs (file content, path, dimension, language), so a
    model switch or a quodeq/standards update reuses the cached result. The
    volatile context is recorded on the entry's provenance at write time.

    MUST stay byte-for-byte identical to the key built in
    ``cache_writer.build_cache_writer`` and ``cache.runner._key_for`` —
    ``CacheKey`` is the single source of truth and all three populate exactly
    its fields.
    """
    content_hash = _hash_file(config.src / file_path) or ""
    key = CacheKey(
        schema_version=_SCHEMA_VERSION,
        file_content_hash=content_hash,
        file_path=file_path,
        dimension=dimension,
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

    cached_findings: list[dict] = []
    misses: list[str] = []
    miss_keys: dict[str, str] = {}
    provenance_drift: dict = {}
    current_prov: dict | None = None  # computed lazily, only if there are hits
    for f in files:
        key = build_cache_key_for_file(config, f, dimension)
        hit = None if bypass_reads else cache.get(key)
        if hit is None:
            misses.append(f)
            miss_keys[f] = key
        else:
            cached_findings.extend(hit.findings)
            if current_prov is None:
                current_prov = _current_provenance(config, dimension)
            _accumulate_drift(provenance_drift, hit.provenance or {}, current_prov)
    result = ClassifyResult(
        cached_findings=cached_findings,
        misses=misses,
        miss_keys=miss_keys,
        provenance_drift=provenance_drift,
    )
    if not bypass_reads and run_cache is not None:
        run_cache[dimension] = (files_tuple, result)
    return result


def _group_findings_by_file(jsonl_path: Path) -> tuple[dict[str, list[dict]], set[str]]:
    """Read a JSONL of findings + markers and return (grouped_findings, ok_files).

    Marker lines are recognised by the ``_marker`` key and excluded from the
    grouped findings. ``ok_files`` contains the set of files whose *most
    recent* file_done marker has status='ok'. Files whose latest marker is
    'error' (or have no marker at all) are not in the set.
    """
    grouped: dict[str, list[dict]] = {}
    last_status: dict[str, str] = {}
    if not jsonl_path.is_file():
        return grouped, set()
    try:
        text = jsonl_path.read_text(encoding="utf-8")
    except OSError as exc:
        _logger.warning("failed to read JSONL %s: %s", jsonl_path, exc)
        return grouped, set()
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if entry.get("_marker") == "file_done":
            f = entry.get("file")
            status = entry.get("status")
            if isinstance(f, str) and status in ("ok", "error"):
                last_status[f] = status
            continue
        f = entry.get("file")
        if isinstance(f, str) and f:
            grouped.setdefault(f, []).append(entry)
    ok_files = {f for f, s in last_status.items() if s == "ok"}
    return grouped, ok_files


def persist_dispatch_results(
    config: RunConfig, dimension: str, *, miss_files: list[str],
    jsonl_path: Path, miss_keys: dict[str, str], cache: CacheBackend,
) -> None:
    """Write per-file cache entries for files with a file_done='ok' marker.

    Files in *miss_files* that lack an ok marker (worker crashed, token-out,
    abandoned) are NOT cached, so the next run re-dispatches them.
    """
    if not jsonl_path.is_file():
        return
    grouped, ok_files = _group_findings_by_file(jsonl_path)
    model_id = _model_id_from(config)
    # Provenance context — run-constant, computed once. These left the cache
    # key in schema 3; recording them keeps each entry self-describing.
    standards_hash = (
        _hash_standards(config.standards_dir, dimension, config.src)
        if config.standards_dir else ""
    ) or ""
    prompts_hash = _hash_prompts_combined()
    version = quodeq_version()
    for f in miss_files:
        if f not in ok_files:
            continue
        key = miss_keys.get(f)
        if key is None:
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
            file_content_hash=_hash_file(config.src / f) or "",
            language=config.language or "",
            provenance=build_provenance(
                model_id=model_id, prompts_hash=prompts_hash,
                standards_hash=standards_hash, version=version,
            ),
        )
        cache.put(key, entry)
