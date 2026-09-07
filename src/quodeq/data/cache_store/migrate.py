"""One-time cache maintenance: schema migration, content-index build, legacy GC.

Entries are self-describing (every key input is stored), so a key-formula
change is a lossless re-key rather than a re-evaluation. This module walks
the cache once per (root, schema):

1. schema 3 entries are re-keyed to schema 4 (``language`` left the key),
   written under the new key, then removed from the old path;
2. schema 4 entries get a content-index row (the walk doubles as the index
   build);
3. anything older than schema 3, or unmigratable, is reclaimed;
4. the index is marked built and ``<root>/.schema_4_ready`` is written.

Best-effort and resumable: each entry is either at its old path or its new
path, never both and never neither, because the new file is renamed into
place before the old directory is removed. An unreadable entry is skipped
and logged. The walk runs under ``<root>/.migrate.lock``; a live lock means
another process is on it and this process simply proceeds with the partially
migrated cache (a few extra misses). A lock older than ``STALE_LOCK_S`` is
taken over.

Ordering matters: the GC must never run ahead of the migration, or it would
delete schema-3 entries that were about to be re-keyed. That is why both live
in one walk here and ``analysis.cache.gc`` is a shim over this module.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, replace
from pathlib import Path

from quodeq.core.standards.overrides import (
    hash_non_default_params,
    non_default_from_effective,
)
from quodeq.data.cache_store.entry import ENTRY_FORMAT_VERSION, CacheEntry
from quodeq.data.cache_store.index import ContentIndex
from quodeq.data.cache_store.key import SCHEMA_VERSION, CacheKey, compute_key
from quodeq.data.cache_store.local import LocalFileBackend

_logger = logging.getLogger(__name__)

_ENTRY_FILENAME = "entry.json"  # mirrors local._ENTRY_FILENAME
LOCK_FILENAME = ".migrate.lock"
STALE_LOCK_S = 1800.0
_BATCH = 500

# (root, schema) pairs known ready in this process.
_ready_memo: set[tuple[str, int]] = set()


def ready_marker(root: Path) -> Path:
    return root / f".schema_{SCHEMA_VERSION}_ready"


@dataclass(frozen=True)
class MigrationStats:
    migrated: int = 0
    deduplicated: int = 0
    indexed: int = 0
    removed: int = 0
    skipped: int = 0


def derive_params_hash(
    dimension: str, effective_params: dict, standards_dir: Path | None,
) -> str:
    """Rebuild a schema-3 entry's ``params_hash`` from its stored effective params.

    The writer hashed the non-default subset against the compiled defaults
    (``analysis.fingerprint._compute_dimension_params``). Diff the stored
    effective map against the current compiled defaults and hash the same way.
    "" when there is nothing to compare (no params, no standards dir, no or
    malformed compiled file), which is exactly what such entries were keyed
    under.
    """
    if not effective_params or standards_dir is None:
        return ""
    compiled = Path(standards_dir) / "compiled" / f"{dimension}.json"
    try:
        data = json.loads(compiled.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - same rationale as the writer: never abort
        return ""
    try:
        return hash_non_default_params(non_default_from_effective(data, effective_params))
    except (AttributeError, TypeError):
        return ""


def _index_row(entry: CacheEntry) -> tuple[str, str, str, str, str, str]:
    return (
        entry.key, entry.file_content_hash, entry.dimension, entry.params_hash,
        entry.file_path, entry.created_at,
    )


def _remove_dir(entry_dir: Path) -> bool:
    try:
        shutil.rmtree(entry_dir)
        return True
    except OSError as exc:
        _logger.debug("cache maintenance: failed to remove %s: %s", entry_dir, exc)
        return False


def _read_entry(entry_path: Path) -> CacheEntry | None:
    try:
        return CacheEntry.from_json(entry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, KeyError, ValueError) as exc:
        _logger.debug("cache maintenance: skipping unreadable entry %s: %s", entry_path, exc)
        return None


def _migrate_v3(
    entry: CacheEntry, entry_dir: Path, backend: LocalFileBackend,
    standards_dir: Path | None, batch: list[tuple],
) -> tuple[int, int]:
    """Re-key one schema-3 entry. Returns (migrated, deduplicated) as 0/1."""
    params_hash = entry.params_hash or derive_params_hash(
        entry.dimension, (entry.provenance or {}).get("effective_params") or {}, standards_dir,
    )
    new_key = compute_key(CacheKey(
        schema_version=SCHEMA_VERSION, file_content_hash=entry.file_content_hash,
        file_path=entry.file_path, dimension=entry.dimension, params_hash=params_hash,
    ))
    if backend.has(new_key):
        _remove_dir(entry_dir)
        return 0, 1
    new_entry = replace(
        entry, key=new_key, schema_version=SCHEMA_VERSION, params_hash=params_hash,
        cache_format_version=ENTRY_FORMAT_VERSION,
    )
    backend.put(new_key, new_entry, index=False)
    if not backend.has(new_key):
        return 0, 0  # write failed (logged by the backend); keep the old entry
    batch.append(_index_row(new_entry))
    _remove_dir(entry_dir)
    return 1, 0


def migrate_entries(
    root: Path, *, standards_dir: Path | None, backend: LocalFileBackend | None = None,
) -> MigrationStats:
    """Walk *root* once: migrate v3, index v4, reclaim older. See module doc."""
    if not root.exists():
        return MigrationStats()
    backend = backend or LocalFileBackend(root=root)
    index = backend.index
    migrated = deduplicated = indexed = removed = skipped = 0
    batch: list[tuple] = []

    def _flush() -> None:
        if batch and index is not None:
            index.record_many(batch)
        batch.clear()

    for entry_path in list(root.rglob(_ENTRY_FILENAME)):
        entry = _read_entry(entry_path)
        if entry is None:
            skipped += 1
            continue
        if entry.schema_version == SCHEMA_VERSION:
            batch.append(_index_row(entry))
            indexed += 1
        elif entry.schema_version == SCHEMA_VERSION - 1:
            m, d = _migrate_v3(entry, entry_path.parent, backend, standards_dir, batch)
            migrated += m
            deduplicated += d
        elif _remove_dir(entry_path.parent):
            removed += 1
        if len(batch) >= _BATCH:
            _flush()
    _flush()
    return MigrationStats(
        migrated=migrated, deduplicated=deduplicated, indexed=indexed,
        removed=removed, skipped=skipped,
    )


def collect_legacy_entries(root: Path, *, min_schema: int) -> int:
    """Delete every entry whose ``schema_version`` is below *min_schema*.

    Kept for callers and tests of the schema-3 GC. ``ensure_cache_ready``
    does this as part of its walk, after migrating what can be migrated.
    """
    if not root.exists():
        return 0
    removed = 0
    for entry_path in root.rglob(_ENTRY_FILENAME):
        try:
            data = json.loads(entry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        schema = data.get("schema_version")
        if isinstance(schema, int) and schema < min_schema and _remove_dir(entry_path.parent):
            removed += 1
    return removed


def _acquire_lock(lock: Path) -> bool:
    """Create *lock* exclusively. A lock older than STALE_LOCK_S is taken over."""
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    for attempt in (0, 1):
        try:
            fd = os.open(lock, flags)
        except FileExistsError:
            if attempt:
                return False
            try:
                age = time.time() - lock.stat().st_mtime
            except OSError:
                return False
            if age < STALE_LOCK_S:
                return False
            try:
                lock.unlink()
            except OSError:
                return False
            continue
        except OSError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
        return True
    return False


def _release_lock(lock: Path) -> None:
    try:
        lock.unlink(missing_ok=True)
    except OSError:
        pass


def _migrate_locked(
    root: Path, *, standards_dir: Path | None, backend: LocalFileBackend,
    index: ContentIndex | None, memo_key: tuple[str, int],
) -> None:
    """Run one migration pass under the lock and record the result."""
    t0 = time.monotonic()
    stats = migrate_entries(root, standards_dir=standards_dir, backend=backend)
    if index is not None:
        index.mark_built(SCHEMA_VERSION)
    ready_marker(root).write_text("", encoding="utf-8")
    _ready_memo.add(memo_key)
    if stats.migrated or stats.removed or stats.indexed:
        _logger.info(
            "cache: schema %d ready in %.1fs (migrated %d, deduplicated %d, "
            "indexed %d, reclaimed %d, skipped %d)",
            SCHEMA_VERSION, time.monotonic() - t0, stats.migrated,
            stats.deduplicated, stats.indexed, stats.removed, stats.skipped,
        )


def ensure_cache_ready(
    root: Path, *, standards_dir: Path | None, backend: LocalFileBackend | None = None,
) -> None:
    """Bring *root* to the current schema with a built index, once.

    Cheap after the first call: an in-process memo, then the on-disk marker
    plus the index's built flag. Never raises. A backend created here (no
    *backend* argument) is local to this call, so its index connection is
    closed before returning rather than left to GC (Windows can't delete an
    open sqlite file out from under a lingering handle).
    """
    memo_key = (str(root), SCHEMA_VERSION)
    if memo_key in _ready_memo:
        return
    if not root.exists():
        _ready_memo.add(memo_key)
        return
    owns_backend = backend is None
    try:
        backend = backend or LocalFileBackend(root=root)
        index = backend.index
        try:
            marker = ready_marker(root)
            if marker.exists() and (index is None or index.built_for_schema() == SCHEMA_VERSION):
                _ready_memo.add(memo_key)
                return
            lock = root / LOCK_FILENAME
            if not _acquire_lock(lock):
                _logger.debug("cache maintenance: %s locked by another process; skipping", root)
                return
            try:
                _migrate_locked(
                    root, standards_dir=standards_dir, backend=backend,
                    index=index, memo_key=memo_key,
                )
            finally:
                _release_lock(lock)
        finally:
            if owns_backend and index is not None:
                index.close()
    except OSError as exc:
        _logger.debug("cache maintenance: best-effort pass failed for %s: %s", root, exc)
