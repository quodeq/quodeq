"""Filesystem I/O for the project index file."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from quodeq.data.fs._index_cache import index_cache

_INDEX_FILE = "project_index.json"
_MAX_LEGACY_SCAN = 500


def _load_index(reports_dir: Path) -> dict[str, str]:
    """Load the project index file, returning an empty dict on missing/corrupt file.

    Uses mtime-based caching to avoid re-reading the file when it hasn't changed.
    """
    index_path = reports_dir / _INDEX_FILE
    try:
        mtime = index_path.stat().st_mtime
    except OSError:
        return {}
    cached = index_cache.get(index_path)
    if cached is not None and cached[0] == mtime:
        return dict(cached[1])  # return a copy so callers can mutate safely
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    index_cache.set(index_path, (mtime, dict(data)))
    return data


def _cleanup_tmp(tmp: str) -> None:
    """Remove a temp file, ignoring errors."""
    try:
        if os.path.exists(tmp):
            os.unlink(tmp)
    except OSError as exc:
        logging.getLogger(__name__).debug("Could not remove temp file %s: %s", tmp, exc)


def _save_index(reports_dir: Path, index: dict[str, str]) -> None:
    """Write the project index file atomically."""
    index_path = reports_dir / _INDEX_FILE
    index_cache.pop(index_path)  # invalidate cache
    tmp = ""
    try:
        fd, tmp = tempfile.mkstemp(dir=reports_dir, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(index, f, indent=2)
        os.replace(tmp, index_path)
    except Exception as exc:
        logging.getLogger(__name__).warning("Could not save project index: %s", exc)
        _cleanup_tmp(tmp)
