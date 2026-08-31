"""Persistent storage for permanently-deleted findings — per-project JSON file.

Unlike the dismissed list (which only excludes findings from scoring), the
deleted list permanently suppresses any finding whose
``(dimension, principle, file)`` matches an entry. Future scans will not
surface those findings again. Deletion is one-way: there is no restore.

The on-disk file ``deleted.json`` lives next to ``dismissed.json``; its
format and lock mechanics live in ``quodeq.data.fs.deleted_store`` — this
module keeps the business rules only (key semantics, deduplication,
sweeping matching dismissed entries).
"""
from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from quodeq.data.ports.actions_log import ActionLog
from quodeq.services.dismissed import load_dismissed
from quodeq.services._wiring import (
    ActionLogWriter,
    find_dismissed_matching,
    locked_deleted_store,
    read_deleted_entries,
    write_deleted_entries,
)
from quodeq.services.suppression_keys import is_deleted
from quodeq.core.events.models import (
    FindingUndismissed,
    FindingUndismissedEvent,
)
from quodeq.core.types.finding import Finding
from quodeq.services.dismissed import recount_totals


_logger = logging.getLogger(__name__)


def _key(entry: dict) -> tuple:
    return (
        entry.get("dimension", "") or "",
        entry.get("principle", "") or "",
        entry.get("file", "") or "",
    )


def load_deleted(project_dir: Path) -> list[dict]:
    """Load deleted suppressions for a project. Returns empty list if none."""
    return read_deleted_entries(project_dir)


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


def delete_finding(project_dir: Path, finding: dict, *, writer: ActionLog | None = None) -> int:
    """Permanently suppress a finding by (dimension, principle, file).

    Also undismisses any dismissed findings that share the same suppression
    key, so the dismissed list stays clean. Returns the number of dismissed
    entries swept (0 if none).
    """
    new_key = _key(finding)
    if not new_key[1] or not new_key[2]:
        return 0
    swept = 0
    with locked_deleted_store(project_dir):
        existing = load_deleted(project_dir)
        if new_key not in {_key(e) for e in existing}:
            existing.append(_entry_from_finding(finding))
            write_deleted_entries(project_dir, existing)
        swept = _sweep_dismissed_matching(project_dir, new_key, writer=writer)
    return swept


def delete_all_dismissed(project_dir: Path, *, writer: ActionLog | None = None) -> int:
    """Convert every currently-dismissed entry into a permanent suppression.

    Reads dismissed findings from each run's evaluation.db, adds a deleted
    entry for each unique ``(dimension, principle, file)`` pair, then
    undismisses all of them via the action log.
    Returns the count of dismissed entries removed.
    """
    with locked_deleted_store(project_dir):
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
        write_deleted_entries(project_dir, existing)
        # Undismiss all via the action log.
        count = len(dismissed_entries)
        log = writer or ActionLogWriter(project_dir)
        for entry in dismissed_entries:
            payload = FindingUndismissed(
                req=entry.get("req", ""),
                file=entry.get("file", ""),
                line=int(entry.get("line", 0)),
            )
            log.emit(FindingUndismissedEvent(payload=payload))
        return count


def _sweep_dismissed_matching(
    project_dir: Path, key: tuple, *, writer: ActionLog | None = None,
) -> int:
    """Undismiss every dismissed finding whose ``(dimension, principle, file)`` matches *key*.

    Reads from each run's evaluation.db (via the data layer's
    ``find_dismissed_matching``) to find dismissed findings that match the
    deletion key, then appends FindingUndismissedEvent to actions.jsonl for each.
    """
    dimension, principle, file = key
    if not project_dir.is_dir():
        return 0

    matching: list[tuple[str, str, int]] = []
    for run_dir in project_dir.iterdir():
        if not run_dir.is_dir():
            continue
        matching.extend(
            find_dismissed_matching(
                run_dir, dimension=dimension, practice_id=principle, file=file,
            )
        )

    if not matching:
        return 0

    log = writer or ActionLogWriter(project_dir)
    for req, f, line in matching:
        payload = FindingUndismissed(req=req, file=f, line=line)
        log.emit(FindingUndismissedEvent(payload=payload))
    return len(matching)


def is_finding_deleted(
    deleted: set[tuple],
    *,
    dimension: str,
    principle: str,
    file: str,
) -> bool:
    """Return True if ``(dimension, principle, file)`` is in *deleted*."""
    return is_deleted(deleted, dimension=dimension, principle=principle, file=file)


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
            if not is_finding_deleted(keys, dimension=dim_id,
                                      principle=_principle_of(v), file=v.file or "")
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
