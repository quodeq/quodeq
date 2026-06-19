"""SQLite implementation of FindingsRepository (per-run evaluation.db)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.core.types.finding import Finding
from quodeq.data.projection.projector import Projector
from quodeq.data.sqlite._row_mappers import (
    finding_dict_to_row,
    row_to_finding,
)
from quodeq.data.sqlite.connection import open_evaluation_db

_INSERT_SQL = """
INSERT OR IGNORE INTO findings (
    schema_version, practice_id, dimension, requirement, verdict, severity,
    file, line, end_line, title, reason, snippet,
    violation_type, context, scope, req_refs_json, dedup_key, confidence
) VALUES (
    :schema_version, :practice_id, :dimension, :requirement, :verdict, :severity,
    :file, :line, :end_line, :title, :reason, :snippet,
    :violation_type, :context, :scope, :req_refs_json, :dedup_key, :confidence
)
"""

_SELECT_COLUMNS = (
    "id, practice_id, dimension, requirement, verdict, severity, "
    "file, line, end_line, title, reason, snippet, "
    "violation_type, context, scope, req_refs_json, confidence"
)


class SqliteFindingsRepository:
    """Per-run findings store backed by evaluation.db in run_dir.

    Reads self-ensure the State Store is fresh against the Event Log
    (``events.jsonl``) before returning rows, so callers above the data
    layer never need to project explicitly. Writes do not trigger projection.
    """

    def __init__(
        self,
        run_dir: Path,
        *,
        projector: Projector | None = None,
        events_log: Path | None = None,
    ) -> None:
        self._run_dir = run_dir
        self._projector = projector or Projector()
        self._events_log = events_log or (run_dir / "events.jsonl")

    def _ensure_fresh(self) -> None:
        if self._events_log.is_file():
            project_dir = self._run_dir.parent
            self._projector.ensure_projected(
                self._events_log,
                self._run_dir,
                project_dir=project_dir,
            )

    def insert_finding(self, finding: dict[str, Any]) -> bool:
        row = finding_dict_to_row(finding)
        with open_evaluation_db(self._run_dir) as conn:
            cur = conn.execute(_INSERT_SQL, row)
            conn.commit()
            return cur.rowcount == 1

    def list_by_dimension(self, dimension: str) -> list[Finding]:
        self._ensure_fresh()
        with open_evaluation_db(self._run_dir) as conn:
            conn.row_factory = _dict_row
            rows = conn.execute(
                f"SELECT {_SELECT_COLUMNS} FROM findings WHERE dimension = ? ORDER BY id",
                (dimension,),
            ).fetchall()
        return [row_to_finding(r) for r in rows]

    def list_all(self) -> list[Finding]:
        """Return every finding in the DB in a single query (all dimensions).

        Callers that need findings grouped by dimension should use this method
        and group in Python rather than issuing N ``list_by_dimension`` calls.
        """
        self._ensure_fresh()
        with open_evaluation_db(self._run_dir) as conn:
            conn.row_factory = _dict_row
            rows = conn.execute(
                f"SELECT {_SELECT_COLUMNS} FROM findings ORDER BY id",
            ).fetchall()
        return [row_to_finding(r) for r in rows]

    def count_by_dimension(self) -> dict[str, int]:
        self._ensure_fresh()
        with open_evaluation_db(self._run_dir) as conn:
            rows = conn.execute(
                "SELECT dimension, COUNT(*) FROM findings GROUP BY dimension",
            ).fetchall()
        return {dim: n for dim, n in rows}

    def search(self, query: str, limit: int = 100) -> list[Finding]:
        self._ensure_fresh()
        fts_query = _quote_fts_query(query)
        with open_evaluation_db(self._run_dir) as conn:
            conn.row_factory = _dict_row
            rows = conn.execute(
                f"SELECT {_SELECT_COLUMNS} FROM findings "
                "WHERE id IN (SELECT rowid FROM findings_fts WHERE findings_fts MATCH ?) "
                "ORDER BY id LIMIT ?",
                (fts_query, limit),
            ).fetchall()
        return [row_to_finding(r) for r in rows]

    def set_verdict(self, *, practice_id: str, file: str, line: int, verdict: str) -> int:
        with open_evaluation_db(self._run_dir) as conn:
            cur = conn.execute(
                "UPDATE findings SET verdict = ? "
                "WHERE practice_id = ? AND file = ? AND line = ?",
                (verdict, practice_id, file, line),
            )
            conn.commit()
            return cur.rowcount


def _dict_row(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def _quote_fts_query(query: str) -> str:
    """Wrap user input as an FTS5 phrase, escaping embedded quotes.

    FTS5 query syntax includes operators (AND/OR/NOT, NEAR, prefix `*`,
    column qualifier `:`). Treating arbitrary user input as a phrase makes
    those characters literal, so a query like `foo:` or `a-b` searches for
    that exact text instead of raising or matching unexpectedly.
    """
    escaped = query.replace('"', '""')
    return f'"{escaped}"'
