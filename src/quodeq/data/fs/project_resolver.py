"""Persistent UUID-based project identity resolution for the reports directory."""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Protocol

_INDEX_FILE = "project_index.json"
_MAX_LEGACY_SCAN = 500

_INDEX_CACHE_MAX = 64


class _IndexCache:
    """Thread-safe mtime-based cache for the project index file (bounded)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[Path, tuple[float, dict[str, str]]] = {}

    def get(self, key: Path) -> tuple[float, dict[str, str]] | None:
        with self._lock:
            return self._data.get(key)

    def set(self, key: Path, value: tuple[float, dict[str, str]]) -> None:
        with self._lock:
            if len(self._data) >= _INDEX_CACHE_MAX and key not in self._data:
                # Evict oldest entry
                oldest = next(iter(self._data))
                del self._data[oldest]
            self._data[key] = value

    def pop(self, key: Path) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


# Module-level singleton for mtime-based project index caching.
# Thread-safe via internal locking (_IndexCache._lock).  Bounded to
# _INDEX_CACHE_MAX entries to prevent unbounded memory growth.
# Call _index_cache.clear() (or clear_index_cache()) in tests for isolation.
_index_cache = _IndexCache()


def clear_index_cache() -> None:
    """Clear the mtime-based index cache (useful for testing and isolation)."""
    _index_cache.clear()


class ProjectRepository(Protocol):
    """Abstraction over the storage layer used to persist project identities.

    Implement this protocol to swap the default filesystem backend for a
    different storage technology (database, cloud object store, etc.) without
    changing any callers of ``resolve_project_uuid``.
    """

    def load_index(self, reports_dir: Path) -> dict[str, str]:
        """Load the name->uuid mapping. Return empty dict on missing/corrupt data."""
        ...

    def save_index(self, reports_dir: Path, index: dict[str, str]) -> None:
        """Persist the name->uuid mapping."""
        ...


@dataclass(frozen=True)
class ProjectIdentity:
    """Identifies a project by name, resolved repo path, and metadata."""
    project_name: str
    repo_path: str
    discipline: str | None = None
    location: str = "local"


def _index_key(identity: ProjectIdentity) -> str:
    """Return a stable string key for the (name, path) pair."""
    return f"{identity.project_name}\x00{identity.repo_path}"


def _load_index(reports_dir: Path) -> dict[str, str]:
    """Load the project index file, returning an empty dict on missing/corrupt file.

    Uses mtime-based caching to avoid re-reading the file when it hasn't changed.
    """
    index_path = reports_dir / _INDEX_FILE
    try:
        mtime = index_path.stat().st_mtime
    except OSError:
        return {}
    cached = _index_cache.get(index_path)
    if cached is not None and cached[0] == mtime:
        return dict(cached[1])  # return a copy so callers can mutate safely
    try:
        data = json.loads(index_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    _index_cache.set(index_path, (mtime, dict(data)))
    return data


def _save_index(reports_dir: Path, index: dict[str, str]) -> None:
    """Write the project index file atomically."""
    index_path = reports_dir / _INDEX_FILE
    _index_cache.pop(index_path)  # invalidate cache
    try:
        fd, tmp = tempfile.mkstemp(dir=reports_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(index, f, indent=2)
            os.replace(tmp, index_path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError as exc:
                    logging.getLogger(__name__).debug("Could not remove temp file %s: %s", tmp, exc)
    except OSError as exc:
        logging.getLogger(__name__).warning("Could not save project index: %s", exc)


def _find_existing_project(
    reports_dir: Path,
    identity: ProjectIdentity,
    load_fn: Callable[[Path], dict[str, str]] = _load_index,
    save_fn: Callable[[Path, dict[str, str]], None] = _save_index,
) -> str | None:
    """Look up project by (name, path) in the index; fall back to directory scan for
    projects created before the index existed, updating the index on success."""
    key = _index_key(identity)
    index = load_fn(reports_dir)
    if key in index:
        # Verify the directory still exists (guard against manual deletion)
        if (reports_dir / index[key]).is_dir():
            return index[key]
        # Index is stale -- remove the entry and fall through to scan
        del index[key]
        save_fn(reports_dir, index)

    # Legacy scan: find projects created before the index was introduced.
    # Bounded to _MAX_LEGACY_SCAN entries to avoid O(n) disk I/O on large collections.
    scanned = 0
    for entry in reports_dir.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        scanned += 1
        if scanned > _MAX_LEGACY_SCAN:
            break
        info_file = entry / "repository_info.json"
        if not info_file.exists():
            continue
        try:
            info = json.loads(info_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if info.get("name") == identity.project_name and info.get("path") == identity.repo_path:
            # Back-fill the index so future lookups are O(1)
            index[key] = entry.name
            save_fn(reports_dir, index)
            return entry.name
    return None


def _create_project(
    reports_dir: Path,
    identity: ProjectIdentity,
    load_fn: Callable[[Path], dict[str, str]] = _load_index,
    save_fn: Callable[[Path, dict[str, str]], None] = _save_index,
) -> str:
    """Create a new UUID project directory, write repository_info.json, and index it."""
    project_uuid = str(uuid.uuid4())
    project_dir = reports_dir / project_uuid
    project_dir.mkdir(parents=True, exist_ok=True)
    info = {
        "uuid": project_uuid,
        "name": identity.project_name,
        "discipline": identity.discipline,
        "location": identity.location,
        "path": identity.repo_path,
    }
    try:
        (project_dir / "repository_info.json").write_text(json.dumps(info, indent=2))
    except OSError as exc:
        logging.getLogger(__name__).warning("Could not write repository_info.json: %s", exc)
    index = load_fn(reports_dir)
    index[_index_key(identity)] = project_uuid
    save_fn(reports_dir, index)
    return project_uuid


def resolve_project_uuid(
    reports_dir: Path,
    identity: ProjectIdentity,
    repository: ProjectRepository | None = None,
) -> str:
    """Find or create a UUID project directory matching identity.

    When *repository* is provided, it is used for loading/saving the index
    instead of the default filesystem helpers, making the storage layer
    injectable for testing or alternative backends.
    """
    if identity.location == "online":
        resolved_path = identity.repo_path
    else:
        resolved_path = str(Path(identity.repo_path).resolve())
    resolved = ProjectIdentity(identity.project_name, resolved_path, identity.discipline, identity.location)
    if not reports_dir.exists():
        reports_dir.mkdir(parents=True, exist_ok=True)

    load_fn = repository.load_index if repository is not None else _load_index
    save_fn = repository.save_index if repository is not None else _save_index
    existing = _find_existing_project(reports_dir, resolved, load_fn, save_fn)
    if existing:
        return existing
    return _create_project(reports_dir, resolved, load_fn, save_fn)
