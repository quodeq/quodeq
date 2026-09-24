import re
import sqlite3

from quodeq.assistant.action_status import ActionStatus
from quodeq.assistant.worktree import WorktreeStatus
from quodeq.data.ports.assistant import SessionScope
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


def _check_values(table: str) -> set[str]:
    """The literal values of *table*'s ``status`` CHECK constraint in ASSISTANT_DDL."""
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS {table}.*?CHECK \(status IN \(([^)]*)\)\)",
        ASSISTANT_DDL, re.DOTALL,
    )
    assert match, f"{table} table CHECK not found in ASSISTANT_DDL"
    return {v.strip().strip("'") for v in match.group(1).split(",")}


def test_actions_check_matches_action_status_enum():
    assert _check_values("actions") == {s.value for s in ActionStatus}


def test_worktrees_check_matches_worktree_status_enum():
    assert _check_values("worktrees") == {s.value for s in WorktreeStatus}


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
    repo.create_session(session_id="new", provider="ollama",
                        scope=SessionScope(project_id="proj"))
    assert repo.get_session("new")["project_id"] == "proj"

    check = sqlite3.connect(db)
    assert check.execute("PRAGMA user_version").fetchone()[0] == ASSISTANT_SCHEMA_VERSION
    check.close()
