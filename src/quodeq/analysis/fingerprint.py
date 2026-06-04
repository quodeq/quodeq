"""Content hashing helpers — file, standards, prompts.

Post-V2 (B6.2c): the V1 fingerprint persistence machinery
(``build_fingerprint``, ``save_fingerprint``, ``load_fingerprint``,
``find_previous_fingerprint``, ``_queue_taken_files``) is gone. V2's
content-addressed cache replaces it: per-file entries keyed by a
SHA-256 of every input that affects analysis output.

What survives here are the hash primitives V2 uses to build cache
keys (and that priority scoring uses to detect file changes).
"""
from __future__ import annotations

import functools
import hashlib
from pathlib import Path

from quodeq.config.paths import default_paths

_HASH_CHUNK_SIZE = 1 << 16  # 64 KiB


def _hash_file(path: Path) -> str | None:
    """SHA-256 hash of a file's content, streamed in chunks to limit memory."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(_HASH_CHUNK_SIZE):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


@functools.lru_cache(maxsize=None)
def _hash_file_by_stat(path: Path, size: int, mtime_ns: int) -> str | None:
    """Memoized ``_hash_file`` keyed by (path, size, mtime_ns).

    Standard make/pyc-style invalidation: hashing is the expensive part,
    but ``os.stat`` is cheap. When the file is rewritten its
    ``mtime_ns`` changes, the cache key changes, and we re-hash. Inside
    one ``quodeq evaluate`` process the inputs don't change, so the
    same key is hit thousands of times — exactly the case we want to
    short-circuit. ``size`` is included as a defensive belt-and-braces
    against the (rare) case of an mtime_ns collision on a same-size
    rewrite at the granularity floor of the underlying filesystem.
    """
    # size and mtime_ns are only here to drive the cache key; the actual
    # hashing reads the real bytes off disk.
    _ = (size, mtime_ns)
    return _hash_file(path)


def _stat_key(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return st.st_size, st.st_mtime_ns


def _hash_standards(standards_dir: Path, dimension: str) -> str | None:
    """SHA-256 of the compiled standards JSON for a dimension.

    Uses the same chunked hashing approach as ``_hash_file`` to avoid
    reading the entire file into memory at once.

    Memoized via ``_hash_file_by_stat``: inside one ``quodeq evaluate``
    process the compiled JSON is rewritten only if the user edits it
    mid-run, in which case the new ``mtime_ns`` invalidates the cache
    automatically. Without this cache a 3 K-file dim re-hashes the same
    JSON 3 K times.
    """
    compiled = standards_dir / "compiled" / f"{dimension}.json"
    key = _stat_key(compiled)
    if key is None:
        return None
    return _hash_file_by_stat(compiled, *key)


# Prompts in this set carry the rules that classify a finding (what counts
# as a violation). A change here forces a full re-analysis. Other prompt
# files are framing/scaffolding; their changes flow into the next run's
# prompts naturally without invalidating cached results.
_RULES_BEARING_PROMPTS: frozenset[str] = frozenset({"evaluation_rules.md"})


def _hash_prompts_map(prompts_dir: Path | None = None) -> dict[str, str]:
    """Per-file SHA-256 of every *.md prompt under *prompts_dir*.

    V2's cache key folds these into one combined hash; storing per-file
    enables future selective invalidation if needed. The actual file
    hashing is memoized in ``_hash_file_by_stat`` (keyed by mtime_ns), so
    repeat calls inside one process re-walk the prompts directory (cheap)
    but don't re-read file bytes.
    """
    if prompts_dir is None:
        prompts_dir = default_paths().prompts_dir
    if prompts_dir is None or not prompts_dir.is_dir():
        return {}
    out: dict[str, str] = {}
    for path in sorted(prompts_dir.glob("*.md")):
        key = _stat_key(path)
        if key is None:
            continue
        h = _hash_file_by_stat(path, *key)
        if h:
            out[path.name] = h
    return out


# Expose ``cache_clear`` on the public-ish surface so test fixtures and
# any code that genuinely needs to drop the cache (e.g. after editing
# a prompt mid-process) don't have to reach for the internal helper.
_hash_standards.cache_clear = _hash_file_by_stat.cache_clear  # type: ignore[attr-defined]
_hash_prompts_map.cache_clear = _hash_file_by_stat.cache_clear  # type: ignore[attr-defined]
