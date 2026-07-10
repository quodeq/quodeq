import sqlite3
import time

from quodeq.data.sqlite.assistant_repository import AssistantRepository


def _store(tmp_path):
    store = AssistantRepository(tmp_path / "assistant.db")
    store.create_session(session_id="s1", provider="ollama", project_id="proj")
    return store


def test_worktree_row_lifecycle(tmp_path):
    store = _store(tmp_path)
    row = store.upsert_worktree(session_id="s1", project_id="proj",
                                repo_root="/repo", path="/wt", branch="quodeq/fix-1")
    assert row["status"] == "active" and row["branch"] == "quodeq/fix-1"
    store.set_worktree_status("s1", "applied")
    assert store.get_worktree("s1")["status"] == "applied"
    assert store.list_worktrees("applied", project_id="proj")[0]["session_id"] == "s1"
    assert store.list_worktrees("active", project_id="proj") == []
    # upsert over a terminal row resets it to active with the new path/branch
    row = store.upsert_worktree(session_id="s1", project_id="proj",
                                repo_root="/repo", path="/wt2", branch="quodeq/fix-2")
    assert row["status"] == "active" and row["path"] == "/wt2"


def test_upsert_bumps_created_at_on_reuse(tmp_path):
    store = _store(tmp_path)
    r1 = store.upsert_worktree(session_id="s1", project_id="proj",
                               repo_root="/repo", path="/wt", branch="quodeq/fix-1")
    store.set_worktree_status("s1", "applied")
    time.sleep(0.01)  # ensure a later subsecond timestamp
    r2 = store.upsert_worktree(session_id="s1", project_id="proj",
                               repo_root="/repo", path="/wt2", branch="quodeq/fix-2")
    assert r2["status"] == "active"
    assert r2["created_at"] != r1["created_at"]  # generation bumped


def test_get_worktree_missing(tmp_path):
    assert _store(tmp_path).get_worktree("nope") is None


def test_migration_v2_to_v3(tmp_path):
    # simulate an on-disk v2 db (sessions only is enough for the migration path)
    db = tmp_path / "assistant.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "PRAGMA user_version = 2;\n"
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, provider TEXT NOT NULL,"
        " model TEXT, project_uuid TEXT, run_id TEXT, project_id TEXT,"
        " cli_session_id TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')));"
    )
    conn.commit()
    conn.close()
    store = AssistantRepository(db)
    assert store.get_worktree("x") is None  # forces connect + migration
    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    conn.close()
