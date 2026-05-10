"""Local filesystem cache backend.

Layout (git-style two-char sharding to keep each directory bounded):

    <root>/<sha[:2]>/<sha[2:]>/entry.json

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
import shutil
from pathlib import Path

from quodeq.analysis.cache.backend import CacheStats
from quodeq.analysis.cache.entry import CacheEntry

_logger = logging.getLogger(__name__)

_ROOT_ENV = "QUODEQ_CACHE_ROOT"
_RESULTS_SUBDIR = "results"
_ENTRY_FILENAME = "entry.json"
_TMP_PREFIX = ".tmp."


def default_cache_root() -> Path:
    """Resolve the result cache root, honouring ``QUODEQ_CACHE_ROOT``.

    Returns ``<base>/results`` so this cache is a sibling of the online
    repo cache under the same shared parent directory.
    """
    raw = os.environ.get(_ROOT_ENV, "").strip()
    base = Path(raw) if raw else Path.home() / ".quodeq" / "cache"
    return base / _RESULTS_SUBDIR


class LocalFileBackend:
    """Sharded filesystem cache with atomic writes."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root if root is not None else default_cache_root()

    @property
    def root(self) -> Path:
        return self._root

    def _dir_for(self, key: str) -> Path:
        if len(key) < 3:
            raise ValueError(f"cache key too short: {key!r}")
        return self._root / key[:2] / key[2:]

    def _entry_path(self, key: str) -> Path:
        return self._dir_for(key) / _ENTRY_FILENAME

    def get(self, key: str) -> CacheEntry | None:
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
            except OSError:
                pass
            return None

    def put(self, key: str, entry: CacheEntry) -> None:
        target_dir = self._dir_for(key)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / _ENTRY_FILENAME
        tmp = target_dir / f"{_TMP_PREFIX}{os.getpid()}.{id(entry):x}"
        try:
            tmp.write_text(entry.to_json(), encoding="utf-8")
            os.replace(tmp, target)
        except OSError as exc:
            _logger.warning("cache write failed for %s: %s", key, exc)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def has(self, key: str) -> bool:
        return self._entry_path(key).is_file()

    def delete(self, key: str) -> None:
        target_dir = self._dir_for(key)
        if not target_dir.exists():
            return
        try:
            shutil.rmtree(target_dir)
        except OSError as exc:
            _logger.warning("cache delete failed for %s: %s", key, exc)

    def stats(self) -> CacheStats:
        if not self._root.exists():
            return CacheStats(entries=0, bytes=0)
        entries = 0
        total_bytes = 0
        for entry_path in self._root.rglob(_ENTRY_FILENAME):
            try:
                total_bytes += entry_path.stat().st_size
                entries += 1
            except OSError:
                continue
        return CacheStats(entries=entries, bytes=total_bytes)
