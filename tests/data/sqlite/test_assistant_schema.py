import sqlite3

from quodeq.data.sqlite._assistant_schema import ASSISTANT_DDL, ASSISTANT_SCHEMA_VERSION
from quodeq.data.sqlite.assistant_repository import AssistantRepository


def test_ddl_creates_all_tables_and_sets_version():
    conn = sqlite3.connect(":memory:")
    conn.executescript(ASSISTANT_DDL)
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {"sessions", "messages", "actions", "events"} <= tables
    assert conn.execute("PRAGMA user_version").fetchone()[0] == ASSISTANT_SCHEMA_VERSION


def test_ddl_is_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.executescript(ASSISTANT_DDL)
    conn.executescript(ASSISTANT_DDL)  # must not raise


def test_migrates_v1_db_to_add_project_id(tmp_path):
    # Simulate an existing v1 database (pre-project_id column).
    db = tmp_path / "assistant.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "PRAGMA user_version = 1;\n"
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, provider TEXT NOT NULL,"
        " model TEXT, project_uuid TEXT, run_id TEXT, cli_session_id TEXT,"
        " created_at TEXT NOT NULL DEFAULT (datetime('now')));"
    )
    conn.execute("INSERT INTO sessions (id, provider) VALUES ('old', 'ollama')")
    conn.commit()
    conn.close()

    repo = AssistantRepository(db)
    # First connect runs the migration; existing rows tolerate NULL project_id.
    assert repo.get_session("old")["project_id"] is None
    repo.create_session(session_id="new", provider="ollama", project_id="proj")
    assert repo.get_session("new")["project_id"] == "proj"

    check = sqlite3.connect(db)
    assert check.execute("PRAGMA user_version").fetchone()[0] == ASSISTANT_SCHEMA_VERSION
    check.close()
