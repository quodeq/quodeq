"""SQLite-backed RunIndex (global ~/.quodeq/index.db)."""
from __future__ import annotations

from pathlib import Path

from quodeq.data.ports.run_index import IndexedRun
from quodeq.data.sqlite.connection import open_index_db


class SqliteRunIndex:
    def __init__(self, quodeq_root: Path):
        self._root = quodeq_root

    def record_started(
        self, *, project: str, run_id: str, branch: str | None,
        model: str | None, started_at: str, db_path: str,
    ) -> None:
        with open_index_db(self._root) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO runs "
                "(project, run_id, branch, model, started_at, finished_at, state, db_path) "
                "VALUES (?, ?, ?, ?, ?, NULL, 'running', ?)",
                (project, run_id, branch, model, started_at, db_path),
            )
            conn.commit()

    def record_finished(
        self, *, project: str, run_id: str, finished_at: str, state: str,
    ) -> None:
        with open_index_db(self._root) as conn:
            conn.execute(
                "UPDATE runs SET finished_at = ?, state = ? "
                "WHERE project = ? AND run_id = ?",
                (finished_at, state, project, run_id),
            )
            conn.commit()

    def list_runs(self, *, project: str | None = None, limit: int = 100) -> list[IndexedRun]:
        with open_index_db(self._root) as conn:
            if project is None:
                rows = conn.execute(
                    "SELECT project, run_id, branch, model, started_at, finished_at, state, db_path "
                    "FROM runs ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT project, run_id, branch, model, started_at, finished_at, state, db_path "
                    "FROM runs WHERE project = ? ORDER BY started_at DESC LIMIT ?",
                    (project, limit),
                ).fetchall()
        return [IndexedRun(*r) for r in rows]
