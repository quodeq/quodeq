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

import hashlib
import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar, cast

from quodeq.core.standards.overrides import (
    OVERRIDES_RELPATH,
    dimension_params,
    hash_non_default_params,
)
from quodeq.data.fs.standards_prefs import load_project_overrides
from quodeq.shared.lru import LRUDict

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


def _stat_key(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return st.st_size, st.st_mtime_ns


def _compute_override_hash(project_root: Path) -> str:
    """Hash of the *parsed* resolved threshold overrides mapping.

    Hashes the *parsed* mapping (canonical JSON) rather than raw file
    bytes, so the fingerprint tracks exactly what analysis consumes via
    ``load_project_overrides``: a formatting-only rewrite or a malformed
    file (ignored by analysis) does not shift the hash. Empty overrides
    hash to "" so callers can fall back to the plain standards hash.
    """
    overrides = load_project_overrides(project_root)
    if not overrides:
        return ""
    canonical = json.dumps(overrides, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _compute_dimension_params(compiled: Path, project_root: Path | None) -> tuple[str, dict]:
    """(params_hash, effective_params) for one compiled dimension file."""
    try:
        data = json.loads(compiled.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - keying must never abort analysis
        # Deliberately wider than OSError/ValueError/UnicodeDecodeError:
        # deeply nested JSON overflows the C decoder's call stack and raises
        # RecursionError, a RuntimeError subclass that would otherwise escape.
        # This sits on the per-dimension cache-keying path, so any escape here
        # fails the run rather than degrading to an unkeyed hash.
        return "", {}
    overrides = load_project_overrides(project_root) if project_root else {}
    try:
        effective, non_default = dimension_params(data, overrides)
    except (AttributeError, TypeError):
        # A shape-invalid params block (e.g. a spec that isn't a dict, or a
        # "params" value that isn't a mapping) raises from effective_params.
        # Analysis must never abort over a malformed compiled file -- keying
        # degrades the same way a missing/unparseable file does.
        return "", {}
    if not non_default:
        return "", effective
    return hash_non_default_params(non_default), effective


_K = TypeVar("_K")
_V = TypeVar("_V")
_StatKey = tuple[Path, int, int]
# ``None`` is a real cached value (an unreadable file), so a miss needs a
# sentinel no memoized computation can return.
_MISS = object()


class HashCache:
    """Lock-guarded, bounded LRU cache backing the fingerprint hash memoizers.

    Three independent maps -- file hashes (compiled standards, prompts),
    override hashes, per-dimension params state -- each keyed by a
    ``(path, size, mtime_ns)`` stat tuple (the dimension-params key adds a
    second file's stat), so an edited input misses on its own. The
    module-default instance below is shared by the long-lived dashboard/API
    server (cache maintenance, ``dimension_params_state``), not just one
    ``quodeq evaluate`` process, so every map is a capped LRU: a run's hot
    working set stays resident while stale keys from past runs age out.

    Instantiable so tests get isolated caches with small capacities.
    """

    def __init__(
        self, *, file_capacity: int = 4096,
        override_capacity: int = 1024, params_capacity: int = 1024,
    ) -> None:
        self._lock = threading.Lock()
        self._file_hashes: LRUDict[_StatKey, str | None] = LRUDict(file_capacity)
        self._override_hashes: LRUDict[_StatKey, str] = LRUDict(override_capacity)
        self._dimension_params: LRUDict[
            tuple[Path, int, int, Path | None, int, int], tuple[str, dict]
        ] = LRUDict(params_capacity)

    def _memo(self, table: LRUDict[_K, _V], key: _K, compute: Callable[[], _V]) -> _V:
        """Cached value for *key*; on a miss, *compute* outside the lock, then store."""
        with self._lock:
            hit = table.get(key, _MISS)
        if hit is not _MISS:
            return cast(_V, hit)
        value = compute()
        with self._lock:
            table.put(key, value)
        return value

    def file_hash(self, path: Path, size: int, mtime_ns: int) -> str | None:
        """Memoized :func:`_hash_file`, keyed by (path, size, mtime_ns)."""
        return self._memo(self._file_hashes, (path, size, mtime_ns), lambda: _hash_file(path))

    def override_hash(self, project_root: Path, size: int, mtime_ns: int) -> str:
        """Memoized :func:`_compute_override_hash`, keyed by (path, size, mtime_ns)."""
        return self._memo(
            self._override_hashes, (project_root, size, mtime_ns),
            lambda: _compute_override_hash(project_root),
        )

    def dimension_params_state(
        self, compiled: Path, c_size: int, c_mtime_ns: int,
        project_root: Path | None, o_size: int, o_mtime_ns: int,
    ) -> tuple[str, dict]:
        """Memoized :func:`_compute_dimension_params`, keyed by both files' stats."""
        key = (compiled, c_size, c_mtime_ns, project_root, o_size, o_mtime_ns)
        return self._memo(
            self._dimension_params, key,
            lambda: _compute_dimension_params(compiled, project_root),
        )

    def reset(self) -> None:
        """Drop all cached entries. Test-isolation / mid-run hygiene seam."""
        with self._lock:
            self._file_hashes.clear()
            self._override_hashes.clear()
            self._dimension_params.clear()


_hash_cache = HashCache()


def _hash_overrides(project_root: Path, *, cache: HashCache | None = None) -> str:
    """Hash of ``<project_root>/.quodeq/standards-overrides.json``; "" when
    the file is absent, empty, or malformed (analysis ignores all three)."""
    key = _stat_key(Path(project_root) / OVERRIDES_RELPATH)
    if key is None:
        return ""
    return (cache or _hash_cache).override_hash(Path(project_root), *key)


def dimension_params_state(
    standards_dir: Path | None, dimension: str, project_root: Path | None,
    *, cache: HashCache | None = None,
) -> tuple[str, dict]:
    """(params_hash, effective_params) for *dimension* under *project_root*.

    ``params_hash`` is "" when every effective param equals its declared
    default, the dimension declares no params, or the compiled file is
    missing — so default-config projects key byte-identically to keys
    computed before params existed. ``effective_params`` is the full
    resolved ``{req_id: {param: value}}`` map for entry provenance.

    The returned dict is shared via memoization — treat it as read-only.
    Reads (and populates) *cache*, defaulting to the module-wide instance
    production shares.
    """
    if standards_dir is None:
        return "", {}
    compiled = Path(standards_dir) / "compiled" / f"{dimension}.json"
    ckey = _stat_key(compiled)
    if ckey is None:
        return "", {}
    root = Path(project_root) if project_root else None
    okey = (_stat_key(root / OVERRIDES_RELPATH) if root else None) or (0, 0)
    return (cache or _hash_cache).dimension_params_state(compiled, *ckey, root, *okey)


def _hash_standards(
    standards_dir: Path, dimension: str, project_root: Path | None = None,
    *, cache: HashCache | None = None,
) -> str | None:
    """SHA-256 of the compiled standards JSON for a dimension.

    Uses the same chunked hashing approach as ``_hash_file`` to avoid
    reading the entire file into memory at once.

    When *project_root* is given, the project's threshold overrides
    (``.quodeq/standards-overrides.json``) are folded in, so tuning a
    numeric threshold changes the effective-standards fingerprint even
    though the shared compiled JSON is untouched. The overrides file is
    not per-dimension, so an override on any requirement shifts every
    dimension's hash — deliberately coarse: the hash only feeds entry
    provenance/drift, never the cache key, so the cost is an extra drift
    flag, not a re-evaluation. A project with no (effective) overrides
    hashes byte-identically to the plain compiled JSON, keeping entries
    written before overrides existed quiet.

    Memoized via *cache* (defaulting to the module-wide instance): an
    edited compiled file changes its ``mtime_ns`` and misses on its own.
    Without this cache a 3 K-file dim re-hashes the same JSON 3 K times.
    """
    cache = cache or _hash_cache
    compiled = standards_dir / "compiled" / f"{dimension}.json"
    key = _stat_key(compiled)
    if key is None:
        return None
    base = cache.file_hash(compiled, *key)
    if base is None or project_root is None:
        return base
    overrides_hash = _hash_overrides(project_root, cache=cache)
    if not overrides_hash:
        return base
    return hashlib.sha256(
        f"{base}\x00overrides\x00{overrides_hash}".encode()
    ).hexdigest()


# Prompts in this set carry the rules that classify a finding (what counts
# as a violation). A change here forces a full re-analysis. Other prompt
# files are framing/scaffolding; their changes flow into the next run's
# prompts naturally without invalidating cached results.
_RULES_BEARING_PROMPTS: frozenset[str] = frozenset({"evaluation_rules.md"})


def _hash_prompts_map(
    prompts_dir: Path | None, *, cache: HashCache | None = None,
) -> dict[str, str]:
    """Per-file SHA-256 of every *.md prompt under *prompts_dir*.

    V2's cache key folds these into one combined hash; storing per-file
    enables future selective invalidation if needed. The actual file
    hashing is memoized in *cache* (keyed by mtime_ns, defaulting to the
    module-wide instance production shares), so repeat calls inside one
    process re-walk the prompts directory (cheap) but don't re-read file
    bytes.

    *prompts_dir* is required: callers resolve ``default_paths().prompts_dir``
    themselves (composition-root concern, not this module's).
    """
    cache = cache or _hash_cache
    if prompts_dir is None or not prompts_dir.is_dir():
        return {}
    out: dict[str, str] = {}
    for path in sorted(prompts_dir.glob("*.md")):
        key = _stat_key(path)
        if key is None:
            continue
        h = cache.file_hash(path, *key)
        if h:
            out[path.name] = h
    return out


def reset_hash_caches(cache: HashCache | None = None) -> None:
    """Reset *cache* (defaulting to the module-wide instance). Test-isolation
    / mid-process hygiene seam (e.g. after editing a prompt mid-process)."""
    (cache or _hash_cache).reset()
