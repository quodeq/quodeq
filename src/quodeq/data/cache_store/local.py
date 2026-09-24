"""Local filesystem cache backend.

Layout (git-style two-char sharding to keep each directory bounded):

    <root>/<sha[:2]>/<sha[2:]>/entry.json
    <root>/.index.db          content index sidecar (see ``index.py``)

Writes go via temp file + ``os.rename``, which is atomic on POSIX and on
NTFS for same-volume renames. A reader either sees the previous contents
or the new contents, never a partial. A crash mid-write leaves an
orphaned ``.tmp.*`` file that's skipped by readers and cleaned up on the
next visit to the same directory.

Cache root resolution mirrors ``context/online_cache.py``:
``QUODEQ_CACHE_ROOT`` overrides ``~/.quodeq/cache`` so tests can sandbox.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
from collections.abc import Iterable, Mapping
from pathlib import Path

from quodeq.data.cache_store.backend import CacheStats
from quodeq.data.cache_store.entry import CacheEntry
from quodeq.data.cache_store.index import INDEX_FILENAME, ContentIndex, IndexEntry, IndexRow
from quodeq.shared.env_resolve import resolve_env

_logger = logging.getLogger(__name__)

_ROOT_ENV = "QUODEQ_CACHE_ROOT"
_RESULTS_SUBDIR = "results"
_ENTRY_FILENAME = "entry.json"
_TMP_PREFIX = ".tmp."
# How long stats() may answer from its last walk. The walk stat()s every
# entry file (100k possible), so repeated calls inside this window reuse the
# answer unless this instance changed the tree in between.
_STATS_TTL_S = 30.0
# Content-addressed keys are SHA-256 hex in production; restrict to a
# path-safe charset so a key can never contain '/', '\\', or '..' and
# escape the cache root in _dir_for.
_SAFE_KEY_RE = re.compile(r"[A-Za-z0-9_-]+")
_SHARD_PREFIX_LEN = 2  # two-char <sha[:2]>/<sha[2:]> sharding, see the module docstring
_MIN_KEY_LEN = _SHARD_PREFIX_LEN + 1  # at least one char left after the shard prefix


def default_cache_root(env: Mapping[str, str] | None = None) -> Path:
    """Resolve the result cache root, honouring ``QUODEQ_CACHE_ROOT``.

    Returns ``<base>/results`` so this cache is a sibling of the online
    repo cache under the same shared parent directory. *env* overrides
    ``os.environ`` when provided.
    """
    raw = resolve_env(env).get(_ROOT_ENV, "").strip()
    base = Path(raw) if raw else Path.home() / ".quodeq" / "cache"
    return base / _RESULTS_SUBDIR


class LocalFileBackend:
    """Sharded filesystem cache with atomic writes."""

    def __init__(
        self, root: Path | None = None, *,
        index: ContentIndex | None = None, enable_index: bool = True,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._root = root if root is not None else default_cache_root(env)
        if index is not None:
            self._index: ContentIndex | None = index
        elif enable_index:
            self._index = ContentIndex(self._root / INDEX_FILENAME)
        else:
            self._index = None
        # stats() memo: (monotonic time, mutation count, entries, bytes).
        self._stats_memo: tuple[float, int, int, int] | None = None
        self._mutations = 0

    @property
    def root(self) -> Path:
        """Directory the sharded entry tree and the index sidecar live under."""
        return self._root

    @property
    def index(self) -> ContentIndex | None:
        """The content index beside this root, or None when disabled."""
        return self._index

    def _dir_for(self, key: str) -> Path:
        if len(key) < _MIN_KEY_LEN:
            raise ValueError(f"cache key too short: {key!r}")
        if not _SAFE_KEY_RE.fullmatch(key):
            raise ValueError(f"invalid cache key: {key!r}")
        return self._root / key[:_SHARD_PREFIX_LEN] / key[_SHARD_PREFIX_LEN:]

    def _entry_path(self, key: str) -> Path:
        return self._dir_for(key) / _ENTRY_FILENAME

    def _mark_mutated(self) -> None:
        """Invalidate the stats() memo: this instance changed the entry tree."""
        self._mutations += 1

    def get(self, key: str) -> CacheEntry | None:
        """Read the entry for *key*, or None on a miss.

        Unreadable and corrupt entries count as misses; a corrupt one is
        deleted so the next ``put`` can heal the slot.
        """
        path = self._entry_path(key)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            _logger.warning("cache read failed for %s: %s", key, exc)
            return None
        try:
            return CacheEntry.from_json(text)
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            # Corrupt entry — treat as miss and remove so the next put can heal.
            _logger.warning("cache entry corrupt at %s, removing: %s", path, exc)
            try:
                path.unlink(missing_ok=True)
                self._mark_mutated()
            except OSError as exc:
                _logger.debug("corrupt local cache entry not removed: %s", exc)
            return None

    def put(self, key: str, entry: CacheEntry, *, index: bool = True) -> None:
        """Write *entry* atomically and record it in the content index.

        ``index=False`` skips the index write; the schema migration uses it to
        batch rows itself instead of committing one per entry.
        """
        target_dir = self._dir_for(key)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / _ENTRY_FILENAME
        tmp = target_dir / f"{_TMP_PREFIX}{os.getpid()}.{id(entry):x}"
        try:
            tmp.write_text(entry.to_json(), encoding="utf-8")
            os.replace(tmp, target)
            self._mark_mutated()
            if index and self._index is not None:
                self._index.record(IndexEntry(
                    key=key, content_hash=entry.file_content_hash, dimension=entry.dimension,
                    params_hash=entry.params_hash, file_path=entry.file_path,
                    created_at=entry.created_at,
                ))
        except OSError as exc:
            _logger.warning("cache write failed for %s: %s", key, exc)
            try:
                tmp.unlink(missing_ok=True)
            except OSError as exc:
                _logger.debug("temp cache file not removed after a failed write: %s", exc)

    def has(self, key: str) -> bool:
        """Report whether an entry file exists, without reading or decoding it."""
        return self._entry_path(key).is_file()

    def delete(self, key: str) -> None:
        """Remove the entry directory for *key* and its index row.

        A missing key is a no-op. A failed removal is logged and leaves the
        index row alone rather than pointing it at an entry that still exists.
        """
        target_dir = self._dir_for(key)
        if not target_dir.exists():
            return
        try:
            shutil.rmtree(target_dir)
        except OSError as exc:
            _logger.warning("cache delete failed for %s: %s", key, exc)
            return
        self._mark_mutated()
        if self._index is not None:
            self._index.forget(key)

    def delete_many(self, keys: Iterable[str]) -> int:
        """Remove each key's entry directory, then drop their index rows in one transaction.

        Same per-key rules as :meth:`delete`: a missing key is a no-op and a
        failed removal is logged and keeps its index row. An invalid key is
        logged and skipped. Returns how many entries were removed.
        """
        removed: list[str] = []
        for key in keys:
            try:
                target_dir = self._dir_for(key)
            except ValueError as exc:
                _logger.debug("cache delete skipped an invalid key: %s", exc)
                continue
            if not target_dir.exists():
                continue
            try:
                shutil.rmtree(target_dir)
            except OSError as exc:
                _logger.warning("cache delete failed for %s: %s", key, exc)
                continue
            removed.append(key)
        if removed:
            self._mark_mutated()
            if self._index is not None:
                self._index.forget_many(removed)
        return len(removed)

    def find_by_content(
        self, content_hash: str, dimension: str, params_hash: str,
    ) -> list[IndexRow]:
        """Index rows for entries written with these inputs, newest first.

        Empty when the index is disabled, unavailable, or the hash is blank.
        Rows are hints: callers must verify the entry they point at.
        """
        if self._index is None or not content_hash:
            return []
        return self._index.find(content_hash, dimension, params_hash)

    def stats(self) -> CacheStats:
        """Entry count and total bytes on disk.

        Answered from the last walk for up to ``_STATS_TTL_S``, or until this
        instance puts, deletes or removes a corrupt entry. Changes made behind
        its back (another process, the migration's direct rmtree) show up once
        the memo expires. The mutation count is read before the walk, so a
        concurrent write during the walk invalidates the memo it produces.
        """
        now = time.monotonic()
        memo = self._stats_memo
        if memo is not None and memo[1] == self._mutations and now - memo[0] < _STATS_TTL_S:
            return CacheStats(entries=memo[2], bytes=memo[3])
        mutations = self._mutations
        entries, total_bytes = self._walk_entries()
        self._stats_memo = (now, mutations, entries, total_bytes)
        return CacheStats(entries=entries, bytes=total_bytes)

    def _walk_entries(self) -> tuple[int, int]:
        """One full walk: (entry count, total bytes). The expensive part of stats()."""
        if not self._root.exists():
            return 0, 0
        entries = 0
        total_bytes = 0
        for entry_path in self._root.rglob(_ENTRY_FILENAME):
            try:
                total_bytes += entry_path.stat().st_size
                entries += 1
            except OSError:
                continue
        return entries, total_bytes
