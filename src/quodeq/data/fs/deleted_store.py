"""On-disk mechanics for the per-project ``deleted.json`` suppression file.

services/deleted.py used to read/write/unlink the file and manage its
lock inline. The file format and locking live here; the service keeps
the business rules (what a suppression key is, sweeping matching
dismissed entries). Reads are best-effort (empty list on absent, corrupt,
or non-list payloads); writing an empty list removes the file so an empty
store leaves no artifact behind.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from quodeq.data._file_lock import lock_file, unlock_file

FILENAME = "deleted.json"
_LOCK_FILENAME = "deleted.json.lock"


def deleted_path(project_dir: Path) -> Path:
    """The on-disk path of the project's ``deleted.json``."""
    return project_dir / FILENAME


@contextmanager
def locked_deleted_store(project_dir: Path) -> Iterator[None]:
    """Hold the exclusive ``deleted.json.lock`` for *project_dir*."""
    lock_path = project_dir / _LOCK_FILENAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        lock_file(fd)
        yield
    finally:
        unlock_file(fd)
        os.close(fd)


def read_deleted_entries(project_dir: Path) -> list[dict]:
    """Parsed entries; empty list when absent, corrupt, or not a list."""
    path = deleted_path(project_dir)
    if not path.exists():
        return []
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return items if isinstance(items, list) else []


def write_deleted_entries(project_dir: Path, entries: list[dict]) -> None:
    """Persist *entries*; an empty list removes the file instead."""
    path = deleted_path(project_dir)
    if entries:
        path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    elif path.exists():
        path.unlink()
