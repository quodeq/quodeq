"""Evaluation DB v5..v9 upgrades: added columns/index and their self-healing idempotence."""
import sqlite3
from quodeq.data.sqlite._migrations import apply_evaluation_schema
from quodeq.data.sqlite._schema import EVALUATION_DDL, SCHEMA_VERSION


# Findings table as it existed at SCHEMA_VERSION=5, before issue #656 added
# the provenance_downgrade column. Used to verify the v5 -> v6 upgrade path.
_V5_FINDINGS_DDL = """
    PRAGMA user_version = 5;
    CREATE TABLE findings (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        schema_version  INTEGER NOT NULL DEFAULT 1,
        practice_id     TEXT NOT NULL,
        dimension       TEXT NOT NULL DEFAULT '',
        requirement     TEXT,
        verdict         TEXT NOT NULL CHECK (verdict IN ('violation','compliance','dismissed')),
        severity        TEXT NOT NULL CHECK (severity IN ('critical','major','high','medium','low','minor')),
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
        confidence      INTEGER NOT NULL DEFAULT 100,
        created_at      TEXT NOT NULL DEFAULT (datetime('now'))
    );
"""


def test_fresh_db_has_provenance_downgrade_column_at_default_zero():
    conn = sqlite3.connect(":memory:")
    apply_evaluation_schema(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(findings)")}
    assert "provenance_downgrade" in columns
    # The column default is 0 (not downgraded).
    conn.execute(
        "INSERT INTO findings (practice_id, verdict, severity, dedup_key) "
        "VALUES ('P1', 'violation', 'major', 'k')",
    )
    assert conn.execute(
        "SELECT provenance_downgrade FROM findings WHERE practice_id='P1'"
    ).fetchone()[0] == 0


def test_upgrade_v5_to_v6_adds_provenance_downgrade_column():
    conn = sqlite3.connect(":memory:")
    conn.executescript(_V5_FINDINGS_DDL)
    conn.execute(
        "INSERT INTO findings (practice_id, verdict, severity, dedup_key) "
        "VALUES ('P-5', 'violation', 'major', 'k5')",
    )

    apply_evaluation_schema(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    columns = {row[1] for row in conn.execute("PRAGMA table_info(findings)")}
    assert "provenance_downgrade" in columns
    # Pre-existing rows inherit the default (not downgraded).
    assert conn.execute(
        "SELECT provenance_downgrade FROM findings WHERE practice_id='P-5'"
    ).fetchone()[0] == 0


def test_upgrade_v5_to_v6_idempotent_when_column_already_present():
    """An interrupted v5->v6 migration can leave provenance_downgrade added
    but user_version still 5 (the ALTER committed, the PRAGMA bump didn't).
    Re-running must self-heal to v6, not raise 'duplicate column name'."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(EVALUATION_DDL)        # full v6 schema: column present
    conn.execute("PRAGMA user_version = 5")   # pretend the version bump never landed

    apply_evaluation_schema(conn)             # must not raise

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


# Findings table as it existed at SCHEMA_VERSION=6, before this fix added
# the scope_downgrade_json column. Used to verify the v6 -> v7 upgrade path.
_V6_FINDINGS_DDL = """
    PRAGMA user_version = 6;
    CREATE TABLE findings (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        schema_version  INTEGER NOT NULL DEFAULT 1,
        practice_id     TEXT NOT NULL,
        dimension       TEXT NOT NULL DEFAULT '',
        requirement     TEXT,
        verdict         TEXT NOT NULL CHECK (verdict IN ('violation','compliance','dismissed')),
        severity        TEXT NOT NULL CHECK (severity IN ('critical','major','high','medium','low','minor')),
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
        confidence      INTEGER NOT NULL DEFAULT 100,
        provenance_downgrade INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT NOT NULL DEFAULT (datetime('now'))
    );
"""


def test_fresh_db_has_scope_downgrade_json_column_at_default_null():
    conn = sqlite3.connect(":memory:")
    apply_evaluation_schema(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(findings)")}
    assert "scope_downgrade_json" in columns
    conn.execute(
        "INSERT INTO findings (practice_id, verdict, severity, dedup_key) "
        "VALUES ('P1', 'violation', 'major', 'k')",
    )
    assert conn.execute(
        "SELECT scope_downgrade_json FROM findings WHERE practice_id='P1'"
    ).fetchone()[0] is None


def test_upgrade_v6_to_v7_adds_scope_downgrade_json_column():
    conn = sqlite3.connect(":memory:")
    conn.executescript(_V6_FINDINGS_DDL)
    conn.execute(
        "INSERT INTO findings (practice_id, verdict, severity, dedup_key) "
        "VALUES ('P-6', 'violation', 'major', 'k6')",
    )

    apply_evaluation_schema(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    columns = {row[1] for row in conn.execute("PRAGMA table_info(findings)")}
    assert "scope_downgrade_json" in columns
    # Pre-existing rows inherit the default (no marker).
    assert conn.execute(
        "SELECT scope_downgrade_json FROM findings WHERE practice_id='P-6'"
    ).fetchone()[0] is None


def test_upgrade_v6_to_v7_idempotent_when_column_already_present():
    """Same self-heal guarantee as the other ALTER-based upgrades: a crash
    between the ALTER and the user_version bump must not raise 'duplicate
    column name' on retry."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(EVALUATION_DDL)        # full v7 schema: column present
    conn.execute("PRAGMA user_version = 6")   # pretend the version bump never landed

    apply_evaluation_schema(conn)             # must not raise

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


# Findings table as it existed at SCHEMA_VERSION=7, before this fix added
# the idx_findings_req_file_line index. Used to verify the v7 -> v8 upgrade.
_V7_FINDINGS_DDL = """
    PRAGMA user_version = 7;
    CREATE TABLE findings (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        schema_version  INTEGER NOT NULL DEFAULT 1,
        practice_id     TEXT NOT NULL,
        dimension       TEXT NOT NULL DEFAULT '',
        requirement     TEXT,
        verdict         TEXT NOT NULL CHECK (verdict IN ('violation','compliance','dismissed')),
        severity        TEXT NOT NULL CHECK (severity IN ('critical','major','high','medium','low','minor')),
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
        confidence      INTEGER NOT NULL DEFAULT 100,
        provenance_downgrade INTEGER NOT NULL DEFAULT 0,
        scope_downgrade_json TEXT,
        created_at      TEXT NOT NULL DEFAULT (datetime('now'))
    );
"""


def _has_index(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (name,),
    ).fetchone() is not None


def test_fresh_db_has_req_file_line_index():
    conn = sqlite3.connect(":memory:")
    apply_evaluation_schema(conn)
    assert _has_index(conn, "idx_findings_req_file_line")


def test_upgrade_v7_to_v8_adds_req_file_line_index():
    conn = sqlite3.connect(":memory:")
    conn.executescript(_V7_FINDINGS_DDL)
    conn.execute(
        "INSERT INTO findings (practice_id, verdict, severity, dedup_key) "
        "VALUES ('P-7', 'violation', 'major', 'k7')",
    )

    apply_evaluation_schema(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert _has_index(conn, "idx_findings_req_file_line")
    # Pre-existing rows survive the upgrade untouched.
    assert conn.execute(
        "SELECT practice_id FROM findings WHERE dedup_key='k7'"
    ).fetchone()[0] == "P-7"


def test_upgrade_v7_to_v8_idempotent_when_index_already_present():
    """Same self-heal guarantee as the other upgrades: a crash between the
    CREATE INDEX and the user_version bump must not raise 'index ... already
    exists' on retry."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(EVALUATION_DDL)        # full v8 schema: index present
    conn.execute("PRAGMA user_version = 7")   # pretend the version bump never landed

    apply_evaluation_schema(conn)             # must not raise

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_fresh_db_is_v9_with_violation_type_raw():
    conn = sqlite3.connect(":memory:")
    apply_evaluation_schema(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    columns = {row[1] for row in conn.execute("PRAGMA table_info(findings)")}
    assert "violation_type_raw" in columns


def _v8_db() -> sqlite3.Connection:
    """A DB exactly as v8 left it: current DDL minus the v9 column, stamped 8."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(EVALUATION_DDL)
    conn.execute("ALTER TABLE findings DROP COLUMN violation_type_raw")
    conn.execute("PRAGMA user_version = 8")
    conn.execute(
        "INSERT INTO findings (practice_id, verdict, severity, file, line, dedup_key) "
        "VALUES ('P1', 'violation', 'minor', 'a.py', 10, 'P1|a.py|10|violation')"
    )
    conn.commit()
    return conn


def test_upgrade_v8_to_v9_adds_column_and_keeps_rows():
    conn = _v8_db()
    apply_evaluation_schema(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert conn.execute("SELECT violation_type_raw FROM findings").fetchone() == ("",)


def test_upgrade_v8_to_v9_idempotent_when_column_already_present():
    """The ALTER and the user_version bump commit separately; a crash between
    them leaves the column added and the version at 8. Re-running must not
    raise 'duplicate column name'."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(EVALUATION_DDL)
    conn.execute("PRAGMA user_version = 8")
    apply_evaluation_schema(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


# Very old (v1/v2) DBs never created `findings`; every additive upgrade skips
# rather than raising "no such table" and bricking the run.
def test_additive_upgrades_skip_a_db_without_findings():
    from quodeq.data.sqlite import _migrations_additive as additive

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY)")
    for upgrade in (additive._upgrade_v5_to_v6, additive._upgrade_v6_to_v7,
                    additive._upgrade_v7_to_v8, additive._upgrade_v8_to_v9):
        upgrade(conn)  # must not raise
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"runs"}
    conn.close()


def test_table_exists_reports_presence():
    from quodeq.data.sqlite._migrations_additive import _table_exists

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE findings (id INTEGER PRIMARY KEY)")
    assert _table_exists(conn, "findings") is True
    assert _table_exists(conn, "absent") is False
    conn.close()
