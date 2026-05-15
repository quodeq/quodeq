"""Persistent storage for permanently-deleted findings — per-project JSON file.

Unlike the dismissed list (which only excludes findings from scoring), the
deleted list permanently suppresses any finding whose
``(dimension, principle, file)`` matches an entry. Future scans will not
surface those findings again. Deletion is one-way: there is no restore.

The on-disk file ``deleted.json`` lives next to ``dismissed.json`` and is
guarded by the same kind of POSIX file lock used by ``dismissed.py``.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

from quodeq.core.types.finding import Finding
from quodeq.data._file_lock import lock_file, unlock_file
from quodeq.services.dismissed import load_dismissed, recount_totals


@runtime_checkable
class DeletedStoreProtocol(Protocol):
    """Abstraction for permanent-suppression storage."""

    def load(self, project_dir: Path) -> list[dict]: ...
    def delete(self, project_dir: Path, finding: dict) -> None: ...
    def delete_all_dismissed(self, project_dir: Path) -> int: ...


_FILENAME = "deleted.json"


def _deleted_path(project_dir: Path) -> Path:
    return project_dir / _FILENAME


@contextmanager
def _locked(project_dir: Path):
    lock_path = project_dir / "deleted.json.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        lock_file(fd)
        yield
    finally:
        unlock_file(fd)
        os.close(fd)


def _key(entry: dict) -> tuple:
    return (
        entry.get("dimension", "") or "",
        entry.get("principle", "") or "",
        entry.get("file", "") or "",
    )


def load_deleted(project_dir: Path) -> list[dict]:
    """Load deleted suppressions for a project. Returns empty list if none."""
    path = _deleted_path(project_dir)
    if not path.exists():
        return []
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(items, list):
        return []
    return items


def deleted_keys(project_dir: Path) -> set[tuple]:
    """Return ``{(dimension, principle, file)}`` tuples for the project."""
    return {_key(e) for e in load_deleted(project_dir)}


def _entry_from_finding(finding: dict) -> dict:
    return {
        "dimension": finding.get("dimension", ""),
        "principle": finding.get("principle", ""),
        "file": finding.get("file", ""),
        "deleted_at": datetime.now(timezone.utc).isoformat(),
    }


def _write_deleted(project_dir: Path, entries: list[dict]) -> None:
    path = _deleted_path(project_dir)
    if entries:
        path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    elif path.exists():
        path.unlink()


def delete_finding(project_dir: Path, finding: dict) -> int:
    """Permanently suppress a finding by (dimension, principle, file).

    Also removes any entries from ``dismissed.json`` that share the same
    suppression key, so the dismissed list stays clean. Returns the number
    of dismissed entries swept (0 if none).
    """
    new_key = _key(finding)
    if not new_key[1] or not new_key[2]:
        return 0
    swept = 0
    with _locked(project_dir):
        existing = load_deleted(project_dir)
        if new_key not in {_key(e) for e in existing}:
            existing.append(_entry_from_finding(finding))
            _write_deleted(project_dir, existing)
        swept = _sweep_dismissed_matching(project_dir, new_key)
    return swept


def delete_all_dismissed(project_dir: Path) -> int:
    """Convert every currently-dismissed entry into a permanent suppression.

    Adds a deleted entry for each unique ``(dimension, principle, file)``
    pair found in ``dismissed.json``, then clears the dismissed list.
    Returns the count of dismissed entries removed.
    """
    with _locked(project_dir):
        dismissed_entries = load_dismissed(project_dir)
        if not dismissed_entries:
            return 0
        existing = load_deleted(project_dir)
        existing_keys = {_key(e) for e in existing}
        for entry in dismissed_entries:
            k = _key(entry)
            if not k[1] or not k[2] or k in existing_keys:
                continue
            existing.append(_entry_from_finding(entry))
            existing_keys.add(k)
        _write_deleted(project_dir, existing)
        # Clear dismissed.json now that everything is permanently suppressed.
        dismissed_path = project_dir / "dismissed.json"
        count = len(dismissed_entries)
        if dismissed_path.exists():
            dismissed_path.unlink()
        return count


def _sweep_dismissed_matching(project_dir: Path, key: tuple) -> int:
    """Remove every dismissed entry whose ``(dimension, principle, file)`` matches *key*."""
    dismissed_path = project_dir / "dismissed.json"
    if not dismissed_path.exists():
        return 0
    try:
        entries = json.loads(dismissed_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(entries, list):
        return 0
    kept = [e for e in entries if _key(e) != key]
    swept = len(entries) - len(kept)
    if swept == 0:
        return 0
    if kept:
        dismissed_path.write_text(json.dumps(kept, indent=2), encoding="utf-8")
    else:
        dismissed_path.unlink()
    return swept


def is_finding_deleted(
    deleted: set[tuple],
    *,
    dimension: str,
    principle: str,
    file: str,
) -> bool:
    """Return True if ``(dimension, principle, file)`` is in *deleted*."""
    if not deleted:
        return False
    return (dimension or "", principle or "", file or "") in deleted


def filter_deleted_from_dimensions(
    dimensions: list, project_dir: Path,
) -> list:
    """Return a new list of DimensionResult with permanently-deleted findings removed.

    Mirrors ``filter_dismissed_from_dimensions``: recalculates totals for any
    dimension whose violations were filtered, leaves other fields unchanged.
    """
    keys = deleted_keys(project_dir)
    if not keys:
        return dimensions
    result = []
    for dim in dimensions:
        dim_id = (getattr(dim, "dimension", "") or "")
        filtered = [
            v for v in dim.violations
            if (dim_id, _principle_of(v), v.file or "") not in keys
        ]
        if len(filtered) == len(dim.violations):
            result.append(dim)
        else:
            result.append(replace(
                dim,
                violations=filtered,
                totals=recount_totals(filtered, old_totals=dim.totals),
            ))
    return result


def _principle_of(f: Finding) -> str:
    return f.practice_id or ""
