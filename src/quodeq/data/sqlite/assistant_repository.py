"""SQLite store for assistant sessions, messages, actions, and event frames."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from quodeq.data.sqlite._assistant_schema import (
    ASSISTANT_DDL,
    ASSISTANT_MIGRATIONS,
    ASSISTANT_SCHEMA_VERSION,
)

_BUSY_TIMEOUT_MS = 5000


def _dict_row(cursor: sqlite3.Cursor, row: tuple) -> dict:
    return {d[0]: row[i] for i, d in enumerate(cursor.description)}


class AssistantRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)

    @property
    def db_path(self) -> Path:
        return self._db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                conn.executescript(ASSISTANT_DDL)
            elif version > ASSISTANT_SCHEMA_VERSION:
                raise sqlite3.DatabaseError(
                    f"assistant.db schema v{version} is newer than supported "
                    f"v{ASSISTANT_SCHEMA_VERSION}"
                )
            elif version < ASSISTANT_SCHEMA_VERSION:
                for target, sql in ASSISTANT_MIGRATIONS:
                    if version < target:
                        conn.executescript(sql)
            conn.row_factory = _dict_row
            yield conn
            conn.commit()
        finally:
            conn.close()

    def create_session(self, *, session_id: str, provider: str,
                       model: str | None = None, project_uuid: str | None = None,
                       run_id: str | None = None,
                       project_id: str | None = None) -> dict:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, provider, model, project_uuid, run_id,"
                " project_id) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, provider, model, project_uuid, run_id, project_id),
            )
        return self.get_session(session_id)  # type: ignore[return-value]

    def get_session(self, session_id: str) -> dict | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()

    def set_cli_session_id(self, session_id: str, cli_session_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET cli_session_id = ? WHERE id = ?",
                (cli_session_id, session_id),
            )

    def add_message(self, session_id: str, role: str, content: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content),
            )
            return int(cur.lastrowid)

    def list_messages(self, session_id: str) -> list[dict]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()

    def create_action(self, *, action_id: str, session_id: str, action_type: str,
                      payload: dict, content_hash: str) -> dict:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO actions (id, session_id, action_type, payload_json,"
                " content_hash) VALUES (?, ?, ?, ?, ?)",
                (action_id, session_id, action_type,
                 json.dumps(payload, ensure_ascii=False), content_hash),
            )
        return self.get_action(action_id)  # type: ignore[return-value]

    def get_action(self, action_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM actions WHERE id = ?", (action_id,)
            ).fetchone()
        if row is None:
            return None
        row["payload"] = json.loads(row.pop("payload_json"))
        return row

    def set_action_status(
        self, action_id: str, status: str, *, expected: str | None = None,
    ) -> bool:
        """Set an action's status; return whether a row was updated.

        With ``expected`` the write is a compare-and-set
        (``WHERE id=? AND status=?``), so a caller can atomically claim a
        transition — two concurrent applies of the same action can't both
        win and double-run the side effect. Without ``expected`` the write
        is unconditional (back-compat for the rollback path).
        """
        with self._connect() as conn:
            if expected is None:
                cur = conn.execute(
                    "UPDATE actions SET status = ? WHERE id = ?",
                    (status, action_id),
                )
            else:
                cur = conn.execute(
                    "UPDATE actions SET status = ? WHERE id = ? AND status = ?",
                    (status, action_id, expected),
                )
            return cur.rowcount == 1

    def append_event(self, session_id: str, frame: dict[str, Any]) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO events (session_id, frame_json) VALUES (?, ?)",
                (session_id, json.dumps(frame, ensure_ascii=False)),
            )
            return int(cur.lastrowid)

    def events_after(self, session_id: str, after_seq: int,
                     limit: int = 500) -> list[tuple[int, dict]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT seq, frame_json FROM events WHERE session_id = ? AND seq > ?"
                " ORDER BY seq LIMIT ?",
                (session_id, after_seq, limit),
            ).fetchall()
        return [(r["seq"], json.loads(r["frame_json"])) for r in rows]

    def upsert_worktree(self, *, session_id: str, project_id: str | None,
                        repo_root: str, path: str, branch: str) -> dict:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO worktrees (session_id, project_id, repo_root, path,"
                " branch, status) VALUES (?, ?, ?, ?, ?, 'active')"
                " ON CONFLICT(session_id) DO UPDATE SET project_id=excluded.project_id,"
                " repo_root=excluded.repo_root, path=excluded.path,"
                " branch=excluded.branch, status='active',"
                " created_at=strftime('%Y-%m-%d %H:%M:%f','now')",
                (session_id, project_id, repo_root, path, branch),
            )
        return self.get_worktree(session_id)  # type: ignore[return-value]

    def get_worktree(self, session_id: str) -> dict | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM worktrees WHERE session_id = ?", (session_id,)
            ).fetchone()

    def set_worktree_status(self, session_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE worktrees SET status = ? WHERE session_id = ?",
                (status, session_id),
            )

    def list_worktrees(self, status: str, project_id: str | None = None) -> list[dict]:
        with self._connect() as conn:
            if project_id is None:
                return conn.execute(
                    "SELECT * FROM worktrees WHERE status = ?", (status,)
                ).fetchall()
            return conn.execute(
                "SELECT * FROM worktrees WHERE status = ? AND project_id = ?",
                (status, project_id),
            ).fetchall()
