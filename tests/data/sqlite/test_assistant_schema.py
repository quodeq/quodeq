import sqlite3

from quodeq.data.sqlite._assistant_schema import ASSISTANT_DDL, ASSISTANT_SCHEMA_VERSION


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
