"""Cache-key composition and provenance tracking for the dimension cache.

Split out of ``dimension_helpers.py``: this module owns the fingerprint ->
key formula (``build_cache_key_for_file``) and the provenance drift
comparison (``_current_provenance`` / ``_accumulate_drift`` /
``format_provenance_drift``) that lets ``dimension_helpers.classify_files_via_cache``
report how many reused findings predate the current model / standards /
prompts.

Moves here MUST be verbatim: this is the formula that determines whether a
cache entry is reused or invalidated. Any behavior drift silently
invalidates users' caches.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from quodeq.analysis._types import RunConfig
from quodeq.analysis.cache.entry import quodeq_version
from quodeq.analysis.cache.key import SCHEMA_VERSION as _SCHEMA_VERSION
from quodeq.analysis.cache.key import CacheKey, compute_key
from quodeq.analysis.fingerprint import (
    _hash_file,
    _hash_prompts_map,
    _hash_standards,
    dimension_params_state,
)

# The schema constant and its history live with the key formula in
# ``data/cache_store/key.py``; ``_SCHEMA_VERSION`` is re-exported here for the
# call sites and tests that import it from this module.


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
        "prompts_hash": _hash_prompts_combined(config.prompts_dir),
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


def _hash_prompts_combined(prompts_dir: Path | None) -> str:
    """Hash all rules-bearing prompts into a single SHA-256.

    The fingerprint module stores a per-file map for selective
    invalidation; here we collapse it to one string so the cache key
    stays simple. Any prompt change still invalidates correctly.

    *prompts_dir* is required: callers resolve ``default_paths().prompts_dir``
    (composition-root concern, not this module's).
    """
    pmap = _hash_prompts_map(prompts_dir) or {}
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


def build_cache_key_struct(config: RunConfig, file_path: str, dimension: str) -> CacheKey:
    """The ``CacheKey`` for a (file, dimension) pair under ``config``.

    Exposed as a struct (not only the hash) so classify can reuse the
    content hash and params hash for adoption lookups without hashing the
    file twice. The key is permissive: it depends only on the real per-unit
    inputs (file content, path, dimension, non-default threshold params), so
    a model switch, a language-detection flip or a quodeq/standards update
    reuses the cached result. The volatile context is recorded on the entry's
    provenance at write time.

    MUST stay byte-for-byte identical to the keys built in
    ``cache_writer._write_cache_entry`` and ``cache.runner._key_for`` --
    ``CacheKey`` is the single source of truth and all three populate exactly
    its fields.
    """
    content_hash = _hash_file(config.src / file_path) or ""
    params_hash, _ = dimension_params_state(config.standards_dir, dimension, config.src)
    return CacheKey(
        schema_version=_SCHEMA_VERSION,
        file_content_hash=content_hash,
        file_path=file_path,
        dimension=dimension,
        params_hash=params_hash,
    )


def build_cache_key_for_file(config: RunConfig, file_path: str, dimension: str) -> str:
    """Compute the cache key for a (file, dimension) pair under ``config``.

    Returns a 64-char hex SHA-256. See ``build_cache_key_struct``.
    """
    return compute_key(build_cache_key_struct(config, file_path, dimension))
