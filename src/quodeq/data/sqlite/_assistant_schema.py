"""DDL for the assistant conversation store (~/.quodeq/assistant.db)."""

ASSISTANT_SCHEMA_VERSION = 3

ASSISTANT_DDL = """
PRAGMA user_version = 3;

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT,
    project_uuid TEXT,
    run_id TEXT,
    project_id TEXT,
    cli_session_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS actions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'drafted'
        CHECK (status IN ('drafted', 'applied', 'rejected')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    frame_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, seq);

CREATE TABLE IF NOT EXISTS worktrees (
    session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    project_id TEXT,
    repo_root TEXT NOT NULL,
    path TEXT NOT NULL,
    branch TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'applied', 'pr_created', 'discarded', 'stale')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Ordered forward migrations from an older on-disk schema. Each entry is
# ``(target_version, sql)``; applied in order for any db whose user_version is
# below ASSISTANT_SCHEMA_VERSION. Adding project_id via ALTER keeps existing
# rows (they tolerate NULL project_id).
ASSISTANT_MIGRATIONS: list[tuple[int, str]] = [
    (2, "ALTER TABLE sessions ADD COLUMN project_id TEXT;\n"
        "PRAGMA user_version = 2;"),
    (3, "CREATE TABLE IF NOT EXISTS worktrees (\n"
        "    session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,\n"
        "    project_id TEXT,\n"
        "    repo_root TEXT NOT NULL,\n"
        "    path TEXT NOT NULL,\n"
        "    branch TEXT NOT NULL,\n"
        "    status TEXT NOT NULL DEFAULT 'active'\n"
        "        CHECK (status IN ('active', 'applied', 'pr_created', 'discarded', 'stale')),\n"
        "    created_at TEXT NOT NULL DEFAULT (datetime('now'))\n"
        ");\n"
        "PRAGMA user_version = 3;"),
]
