"""Drop every score-cache row of deleted projects.

The cache is disposable and rebuilt on demand, but its rows outlive a deleted
project otherwise: grades, History change data, and the map's per-finding
payloads, which name files and quote findings.
"""
from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable

from quodeq.data.sqlite.read_only import is_read_only
from quodeq.data.sqlite.score_cache_db import rollback_quietly

_logger = logging.getLogger(__name__)

# Every score-cache table keyed by project (score_cache_schema.SCHEMA). The
# names are formatted into the SQL, so they never come from a caller.
_PROJECT_TABLES = (
    "run_scalars", "run_principle_scalars", "project_summary_cache",
    "run_keys", "run_change", "map_snapshot", "map_finding",
)


def forget_projects(conn: sqlite3.Connection, projects: Iterable[str]) -> None:
    """Delete *projects*' rows from every project-keyed table, in one commit (best-effort)."""
    ids = [(project,) for project in projects]
    if not ids or is_read_only(conn):
        return
    try:
        for table in _PROJECT_TABLES:
            conn.executemany(f"DELETE FROM {table} WHERE project=?", ids)
        conn.commit()
    except sqlite3.Error:
        _logger.warning("score cache purge failed for %d projects", len(ids), exc_info=True)
        rollback_quietly(conn)
