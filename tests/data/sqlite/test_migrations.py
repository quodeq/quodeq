import sqlite3
import pytest
from quodeq.data.sqlite._migrations import (
    apply_evaluation_schema,
    SchemaVersionError,
    _upgrade_v3_to_v4,
)
from quodeq.data.sqlite._schema import SCHEMA_VERSION


# Column list shared by the v3 `findings` table and its renamed `findings_old_v3`.
_V3_FINDINGS_COLUMNS = """
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schema_version INTEGER NOT NULL DEFAULT 1,
    practice_id TEXT NOT NULL,
    dimension TEXT NOT NULL DEFAULT '',
    requirement TEXT,
    verdict TEXT NOT NULL,
    severity TEXT NOT NULL,
    file TEXT NOT NULL DEFAULT '',
    line INTEGER NOT NULL DEFAULT 0,
    end_line INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    snippet TEXT NOT NULL DEFAULT '',
    violation_type TEXT NOT NULL DEFAULT '',
    context TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL DEFAULT '',
    req_refs_json TEXT,
    dedup_key TEXT NOT NULL UNIQUE,
    confidence INTEGER NOT NULL DEFAULT 100,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
"""


def _make_findings_table(conn: sqlite3.Connection, name: str, *, dedup: str) -> None:
    conn.execute(f"CREATE TABLE {name} ({_V3_FINDINGS_COLUMNS})")
    conn.execute(
        f"INSERT INTO {name} (practice_id, verdict, severity, file, line, dedup_key) "
        "VALUES ('P1', 'violation', 'critical', 'a.py', 10, ?)",
        (dedup,),
    )
    conn.commit()


def test_apply_evaluation_schema_on_fresh_db_sets_version():
    conn = sqlite3.connect(":memory:")
    apply_evaluation_schema(conn)
    cur = conn.execute("PRAGMA user_version")
    assert cur.fetchone()[0] == SCHEMA_VERSION


def test_apply_evaluation_schema_creates_findings_and_fts():
    conn = sqlite3.connect(":memory:")
    apply_evaluation_schema(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "findings" in tables
    assert "findings_fts" in tables
    assert "dimension_scores" in tables
    assert "run_meta" in tables


def test_apply_evaluation_schema_idempotent_on_same_version():
    conn = sqlite3.connect(":memory:")
    apply_evaluation_schema(conn)
    # second apply must not fail and must not duplicate
    apply_evaluation_schema(conn)
    cur = conn.execute("PRAGMA user_version")
    assert cur.fetchone()[0] == SCHEMA_VERSION


def test_apply_evaluation_schema_rejects_newer_version():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA user_version = 99")
    with pytest.raises(SchemaVersionError):
        apply_evaluation_schema(conn)


def test_newer_version_error_is_a_database_error():
    """SchemaVersionError must be a sqlite3.DatabaseError so the existing
    `except sqlite3.DatabaseError` guards (e.g. dismissed-list enrichment)
    degrade gracefully instead of crashing when an older binary opens a
    newer-schema evaluation.db."""
    assert issubclass(SchemaVersionError, sqlite3.DatabaseError)
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA user_version = 99")
    with pytest.raises(sqlite3.DatabaseError):
        apply_evaluation_schema(conn)


def _build_v1_db() -> sqlite3.Connection:
    """Recreate the schema as it existed at SCHEMA_VERSION=1, before the
    confidence column was added. Used to verify the v1 → v2 upgrade path."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        PRAGMA user_version = 1;
        CREATE TABLE findings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            schema_version  INTEGER NOT NULL DEFAULT 1,
            practice_id     TEXT NOT NULL,
            dimension       TEXT NOT NULL DEFAULT '',
            requirement     TEXT,
            verdict         TEXT NOT NULL CHECK (verdict IN ('violation','compliance','dismissed')),
            severity        TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low','minor')),
            file            TEXT NOT NULL DEFAULT '',
            line            INTEGER NOT NULL DEFAULT 0,
            end_line        INTEGER NOT NULL DEFAULT 0,
            title           TEXT NOT NULL DEFAULT '',
            reason          TEXT NOT NULL DEFAULT '',
            snippet         TEXT NOT NULL DEFAULT '',
            violation_type  TEXT NOT NULL DEFAULT '',
            context         TEXT NOT NULL DEFAULT '',
            scope           TEXT NOT NULL DEFAULT '',
            req_refs_json   TEXT,
            dedup_key       TEXT NOT NULL UNIQUE,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    return conn


def test_apply_evaluation_schema_upgrades_v1_to_current():
    conn = _build_v1_db()
    # Existing rows in v1 must survive the upgrade and inherit the default 100.
    conn.execute(
        "INSERT INTO findings (practice_id, verdict, severity, dedup_key) "
        "VALUES ('P-1', 'violation', 'medium', 'k1')",
    )
    apply_evaluation_schema(conn)
    cur = conn.execute("PRAGMA user_version")
    assert cur.fetchone()[0] == SCHEMA_VERSION
    cur = conn.execute("SELECT confidence FROM findings WHERE practice_id='P-1'")
    assert cur.fetchone()[0] == 100


def test_upgrade_v3_to_v4_recovers_when_findings_already_renamed():
    """An interrupted v3->v4 migration leaves `findings` renamed to
    `findings_old_v3` with no `findings` table. Re-running the upgrade must
    recover and finish, not raise 'no such table: findings' forever (which
    permanently bricked the run's DB)."""
    conn = sqlite3.connect(":memory:")
    _make_findings_table(conn, "findings_old_v3", dedup="P1|a.py|10|violation")

    _upgrade_v3_to_v4(conn)  # must not raise

    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "findings" in tables
    assert "findings_old_v3" not in tables
    rows = conn.execute("SELECT practice_id, file FROM findings").fetchall()
    assert rows == [("P1", "a.py")]  # data carried in the renamed table survived


def test_upgrade_v3_to_v4_recovers_when_stale_old_table_present():
    """An attempt interrupted before dropping `findings_old_v3` leaves BOTH
    tables. The rebuild's RENAME would fail with 'table findings_old_v3 already
    exists'; the upgrade must drop the stale leftover and finish."""
    conn = sqlite3.connect(":memory:")
    _make_findings_table(conn, "findings", dedup="P1|a.py|10|violation")
    _make_findings_table(conn, "findings_old_v3", dedup="stale")

    _upgrade_v3_to_v4(conn)  # must not raise

    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "findings" in tables
    assert "findings_old_v3" not in tables
    rows = conn.execute("SELECT practice_id, file FROM findings").fetchall()
    assert rows == [("P1", "a.py")]  # authoritative `findings` data kept


def test_apply_evaluation_schema_rejects_unknown_version_with_no_upgrade_path():
    conn = sqlite3.connect(":memory:")
    # Set user_version to a non-zero value with no upgrade path defined.
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 100}")
    with pytest.raises(SchemaVersionError):
        apply_evaluation_schema(conn)
