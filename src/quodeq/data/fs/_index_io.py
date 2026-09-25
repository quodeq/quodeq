"""Filesystem I/O for the project index file."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from quodeq.data.fs._index_cache import IndexCache, index_cache
from quodeq.shared.json_state import dump_json_and_replace

_INDEX_FILE = "project_index.json"
MAX_LEGACY_SCAN = 500


def load_index(reports_dir: Path, *, cache: IndexCache | None = None) -> dict[str, str]:
    """Load the project index file, returning an empty dict on missing/corrupt file.

    Uses mtime-based caching to avoid re-reading the file when it hasn't
    changed. Reads (and writes) *cache*, defaulting to the module-wide
    instance production shares.
    """
    cache = cache or index_cache
    index_path = reports_dir / _INDEX_FILE
    try:
        mtime = index_path.stat().st_mtime
    except OSError:
        return {}
    cached = cache.get(index_path)
    if cached is not None and cached[0] == mtime:
        return dict(cached[1])  # return a copy so callers can mutate safely
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    cache.set(index_path, (mtime, dict(data)))
    return data


def _cleanup_tmp(tmp: str) -> None:
    """Remove a temp file, ignoring errors."""
    try:
        if os.path.exists(tmp):
            os.unlink(tmp)
    except OSError as exc:
        logging.getLogger(__name__).debug("Could not remove temp file %s: %s", tmp, exc)


def save_index(reports_dir: Path, index: dict[str, str], *, cache: IndexCache | None = None) -> None:
    """Write the project index file atomically."""
    cache = cache or index_cache
    index_path = reports_dir / _INDEX_FILE
    cache.pop(index_path)  # invalidate cache
    tmp = ""
    try:
        fd, tmp = tempfile.mkstemp(dir=reports_dir, suffix=".tmp")
        dump_json_and_replace(fd, tmp, index_path, index, indent=2)
    except OSError as exc:
        logging.getLogger(__name__).warning("Could not save project index: %s", exc)
        _cleanup_tmp(tmp)


class FilesystemProjectRepository:
    """The default ``ProjectRepository``: the reports dir's ``project_index.json``."""

    def load_index(self, reports_dir: Path) -> dict[str, str]:
        """Load the index through the module-wide cache (see ``load_index``)."""
        return load_index(reports_dir)

    def save_index(self, reports_dir: Path, index: dict[str, str]) -> None:
        """Write the index atomically (see ``save_index``)."""
        save_index(reports_dir, index)
