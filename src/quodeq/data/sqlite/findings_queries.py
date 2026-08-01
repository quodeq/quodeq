"""Read-only queries over a run's ``findings`` table.

The services layer (dismissed/deleted/run_keys) used to inline this SQL,
which coupled business flows to the schema and pulled sqlite3 into the
service layer. All three reads live here so the schema stays an
adapter-layer detail. Every function is best-effort: an absent or
unreadable database yields empty results, matching the callers'
long-standing behavior.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from quodeq.data.sqlite.connection import open_evaluation_db

_logger = logging.getLogger(__name__)


def read_finding_details(run_dir: Path, keys: set[tuple]) -> dict[tuple, dict]:
    """Return finding-detail dicts for the ``(requirement, file, line)``
    *keys* present in *run_dir*'s findings table.

    Keys not present are simply absent from the result. The SQL ``verdict``
    column is ignored on purpose: actions.jsonl is the source of truth for
    *which* findings are dismissed; the row only supplies *what* the finding
    was. A corrupt database returns whatever was read before the error.
    """
    db_path = run_dir / "evaluation.db"
    if not db_path.is_file():
        return {}
    out: dict[tuple, dict] = {}
    try:
        with open_evaluation_db(run_dir) as conn:
            cursor = conn.execute(
                "SELECT requirement, file, line, dimension, practice_id, severity, "
                "title, reason, snippet, context, scope, end_line, req_refs_json "
                "FROM findings"
            )
            for row in cursor:
                key = (str(row[0] or ""), str(row[1] or ""), int(row[2] or 0))
                if key not in keys or key in out:
                    continue
                req_refs_raw = row[12]
                try:
                    req_refs = json.loads(req_refs_raw) if req_refs_raw else []
                except (json.JSONDecodeError, TypeError):
                    req_refs = []
                out[key] = {
                    "req": row[0] or "", "file": row[1] or "", "line": row[2] or 0,
                    "dimension": row[3] or "", "principle": row[4] or "",
                    "severity": row[5] or "", "title": row[6] or "", "reason": row[7] or "",
                    "snippet": row[8] or "", "context": row[9] or "", "scope": row[10] or "",
                    "endLine": row[11] or 0, "reqRefs": req_refs,
                }
    except sqlite3.DatabaseError:
        return out
    return out


def read_run_key_sets(run_dir: Path) -> tuple[set[tuple], set[tuple]]:
    """Return ``(dismiss_keys, class_keys)`` present in *run_dir*'s findings.

    ``dismiss_keys``: ``{(requirement, file, line)}``.
    ``class_keys``: ``{(dimension, practice_id, file)}``.
    Keys come from ALL findings regardless of verdict, so a dismiss (which
    only flips a verdict) never changes a run's key set.
    """
    db_path = run_dir / "evaluation.db"
    if not db_path.is_file():
        return set(), set()
    dismiss: set[tuple] = set()
    cls: set[tuple] = set()
    try:
        with open_evaluation_db(run_dir) as conn:
            for req, file, line, dim, pid in conn.execute(
                "SELECT requirement, file, line, dimension, practice_id FROM findings"
            ):
                dismiss.add((str(req or ""), str(file or ""), int(line or 0)))
                cls.add((str(dim or ""), str(pid or ""), str(file or "")))
    except sqlite3.DatabaseError:
        return set(), set()
    return dismiss, cls


def find_dismissed_matching(
    run_dir: Path, *, dimension: str, practice_id: str, file: str,
) -> list[tuple[str, str, int]]:
    """Return ``(requirement, file, line)`` for every DISMISSED finding in
    *run_dir* matching the ``(dimension, practice_id, file)`` deletion key."""
    db_path = run_dir / "evaluation.db"
    if not db_path.is_file():
        return []
    try:
        with open_evaluation_db(run_dir) as conn:
            return [
                (row[0] or "", row[1] or "", int(row[2] or 0))
                for row in conn.execute(
                    "SELECT requirement, file, line FROM findings "
                    "WHERE verdict = 'dismissed' AND dimension = ? "
                    "AND practice_id = ? AND file = ?",
                    (dimension, practice_id, file),
                )
            ]
    except (sqlite3.Error, OSError):
        _logger.warning(
            "Skipping unreadable evaluation.db in %s", run_dir, exc_info=True,
        )
        return []
