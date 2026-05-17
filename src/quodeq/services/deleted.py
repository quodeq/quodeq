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

from quodeq.core.events.models import (
    FindingUndismissed,
    FindingUndismissedEvent,
)
from quodeq.core.types.finding import Finding
from quodeq.data._file_lock import lock_file, unlock_file
from quodeq.data.actions_log import ActionLogWriter
from quodeq.services.dismissed import recount_totals


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

    Also undismisses any dismissed findings that share the same suppression
    key, so the dismissed list stays clean. Returns the number of dismissed
    entries swept (0 if none).
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

    Reads dismissed findings from each run's evaluation.db, adds a deleted
    entry for each unique ``(dimension, principle, file)`` pair, then
    undismisses all of them via the action log.
    Returns the count of dismissed entries removed.
    """
    from quodeq.services.dismissed import load_dismissed  # noqa: PLC0415

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
        # Undismiss all via the action log.
        count = len(dismissed_entries)
        writer = ActionLogWriter(project_dir)
        for entry in dismissed_entries:
            payload = FindingUndismissed(
                req=entry.get("req", ""),
                file=entry.get("file", ""),
                line=int(entry.get("line", 0)),
            )
            writer.emit(FindingUndismissedEvent(payload=payload))
        return count


def _sweep_dismissed_matching(project_dir: Path, key: tuple) -> int:
    """Undismiss every dismissed finding whose ``(dimension, principle, file)`` matches *key*.

    Reads from each run's evaluation.db to find dismissed findings that match
    the deletion key, then appends FindingUndismissedEvent to actions.jsonl for each.
    """
    from quodeq.data.sqlite.connection import open_evaluation_db  # noqa: PLC0415

    dimension, principle, file = key
    runs_root = project_dir / "runs"
    if not runs_root.is_dir():
        return 0

    matching: list[tuple[str, str, int]] = []
    for run_dir in runs_root.iterdir():
        if not run_dir.is_dir():
            continue
        db_path = run_dir / "evaluation.db"
        if not db_path.is_file():
            continue
        try:
            with open_evaluation_db(run_dir) as conn:
                for row in conn.execute(
                    "SELECT requirement, file, line FROM findings "
                    "WHERE verdict = 'dismissed' AND dimension = ? "
                    "AND practice_id = ? AND file = ?",
                    (dimension, principle, file),
                ):
                    matching.append((row[0] or "", row[1] or "", int(row[2] or 0)))
        except Exception:
            continue

    if not matching:
        return 0

    writer = ActionLogWriter(project_dir)
    for req, f, line in matching:
        payload = FindingUndismissed(req=req, file=f, line=line)
        writer.emit(FindingUndismissedEvent(payload=payload))
    return len(matching)


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
