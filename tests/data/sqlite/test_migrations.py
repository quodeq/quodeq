import sqlite3
import pytest
from quodeq.data.sqlite._migrations import (
    apply_evaluation_schema,
    SchemaVersionError,
    _upgrade_v3_to_v4,
)
from quodeq.data.sqlite._schema import EVALUATION_DDL, SCHEMA_VERSION


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


def test_upgrade_v3_to_v4_recovers_when_partial_new_table_present():
    """An attempt interrupted after `findings` was recreated but before the
    copy finished leaves BOTH tables: an empty/partial new `findings` and the
    original `findings_old_v3`. The ORIGINAL data must win, otherwise dropping
    findings_old_v3 (and keeping the empty new table) loses every finding."""
    conn = sqlite3.connect(":memory:")
    conn.execute(f"CREATE TABLE findings ({_V3_FINDINGS_COLUMNS})")  # empty new table
    _make_findings_table(conn, "findings_old_v3", dedup="P1|a.py|10|violation")  # original

    _upgrade_v3_to_v4(conn)  # must not raise

    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "findings" in tables
    assert "findings_old_v3" not in tables
    rows = conn.execute("SELECT practice_id, file FROM findings").fetchall()
    assert rows == [("P1", "a.py")]  # original rows recovered, not the empty copy


def test_upgrade_v4_to_v5_idempotent_when_exit_reason_already_present():
    """An interrupted v4->v5 migration can leave dimension_scores.exit_reason
    already added but user_version still 4 (the ALTER committed in autocommit,
    the separate PRAGMA bump never did). Re-running must self-heal to v5, not
    raise 'duplicate column name: exit_reason' -- a bare OperationalError the
    scoring/dashboard read seams don't catch, which permanently bricks the
    run's scores and dashboard with no recovery."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(EVALUATION_DDL)        # full v5 schema: exit_reason present
    conn.execute("PRAGMA user_version = 4")   # pretend the version bump never landed

    apply_evaluation_schema(conn)             # must not raise

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_upgrade_v1_to_v2_idempotent_when_confidence_already_present():
    """An interrupted v1->v2 migration can leave findings.confidence added but
    user_version still 1 (the ALTER committed, the separate PRAGMA bump didn't).
    Re-running must self-heal to v5, not raise 'duplicate column name:
    confidence' -- the same brick-the-run failure class as the other steps."""
    conn = _build_v1_db()
    conn.execute("ALTER TABLE findings ADD COLUMN confidence INTEGER NOT NULL DEFAULT 100")
    # user_version is still 1 (set by _build_v1_db); the bump never landed.

    apply_evaluation_schema(conn)  # must not raise

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_upgrade_v2_to_v3_idempotent_when_principle_grades_already_present():
    """An interrupted v2->v3 migration can leave principle_grades created but
    user_version still 2 (executescript committed the CREATE, the separate
    PRAGMA bump never landed). Re-running must self-heal all the way to v5 and
    preserve rows, not raise 'table principle_grades already exists' -- a bare
    OperationalError the read seams don't catch, which permanently bricks the
    run."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        PRAGMA user_version = 2;
        CREATE TABLE findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schema_version INTEGER NOT NULL DEFAULT 1,
            practice_id TEXT NOT NULL,
            dimension TEXT NOT NULL DEFAULT '',
            requirement TEXT,
            verdict TEXT NOT NULL CHECK (verdict IN ('violation','compliance','dismissed')),
            severity TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low','minor')),
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
        );
        CREATE TABLE dimension_scores (
            dimension TEXT PRIMARY KEY, score REAL, grade TEXT, confidence TEXT,
            files_read INTEGER NOT NULL DEFAULT 0, source_count INTEGER NOT NULL DEFAULT 0,
            coverage_pct REAL NOT NULL DEFAULT 0.0,
            completed_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE run_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        -- an interrupted v2->v3 attempt already created these:
        CREATE TABLE principle_grades (
            dimension TEXT NOT NULL, principle_id TEXT NOT NULL, score REAL, grade TEXT,
            finding_count INTEGER NOT NULL DEFAULT 0, dismissed_count INTEGER NOT NULL DEFAULT 0,
            completed_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (dimension, principle_id)
        );
        CREATE INDEX idx_principle_grades_dimension ON principle_grades(dimension);
        INSERT INTO findings (practice_id, verdict, severity, dedup_key)
            VALUES ('P-2', 'violation', 'high', 'k2');
    """)

    apply_evaluation_schema(conn)  # must not raise

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    # the row survives the full v2->v5 walk (including the v3->v4 table rebuild)
    row = conn.execute("SELECT confidence FROM findings WHERE practice_id='P-2'").fetchone()
    assert row[0] == 100


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


def test_apply_evaluation_schema_rejects_unknown_version_with_no_upgrade_path():
    conn = sqlite3.connect(":memory:")
    # Set user_version to a non-zero value with no upgrade path defined.
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 100}")
    with pytest.raises(SchemaVersionError):
        apply_evaluation_schema(conn)
