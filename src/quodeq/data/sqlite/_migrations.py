"""Apply schema DDL to a fresh SQLite connection. Refuse newer-version DBs."""
from __future__ import annotations

import sqlite3

from quodeq.data.sqlite._migrations_ddl import _V4_REBUILD_DDL
from quodeq.data.sqlite._schema import EVALUATION_DDL, SCHEMA_VERSION


class SchemaVersionError(sqlite3.DatabaseError):
    """Raised when the on-disk DB has a newer schema than this binary supports.

    Subclasses ``sqlite3.DatabaseError`` (not bare ``RuntimeError``) so the
    existing ``except sqlite3.DatabaseError`` guards around evaluation.db reads
    degrade gracefully when an older binary opens a newer-schema DB, instead of
    letting the error escape and crash the read.
    """


def _current_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


# Incremental upgrades from version N to N+1. Each function takes a connection
# already at version N; the caller bumps PRAGMA user_version to N+1 afterwards.
def _upgrade_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Add per-finding confidence column (default 100 = full confidence).

    Idempotency: the ALTER and the PRAGMA user_version bump commit separately,
    so a crash between them leaves the column added but the version still 1.
    Skip if it already exists, otherwise the re-run raises "duplicate column
    name: confidence" and bricks the run (see _upgrade_v4_to_v5 for the same
    guard on exit_reason).
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(findings)")}
    if "confidence" not in columns:
        conn.execute("ALTER TABLE findings ADD COLUMN confidence INTEGER NOT NULL DEFAULT 100")


def _upgrade_v2_to_v3(conn: sqlite3.Connection) -> None:
    """Add principle_grades table for per-principle scoring.

    Idempotency: executescript commits the DDL immediately, independent of the
    later PRAGMA user_version bump in apply_evaluation_schema. A crash between
    them leaves the table created but the version still 2, so re-running a bare
    CREATE would raise "table principle_grades already exists" -- a plain
    OperationalError the scoring/dashboard read seams don't catch, permanently
    bricking the run. IF NOT EXISTS makes the re-run a no-op and self-heal.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS principle_grades (
            dimension        TEXT NOT NULL,
            principle_id     TEXT NOT NULL,
            score            REAL,
            grade            TEXT,
            finding_count    INTEGER NOT NULL DEFAULT 0,
            dismissed_count  INTEGER NOT NULL DEFAULT 0,
            completed_at     TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (dimension, principle_id)
        );

        CREATE INDEX IF NOT EXISTS idx_principle_grades_dimension ON principle_grades(dimension);
    """)


def _recover_v4_rebuild_state(conn: sqlite3.Connection) -> None:
    """Normalise findings/findings_old_v3 before ``_upgrade_v3_to_v4`` rebuilds.

    Recovery: the rebuild renames ``findings`` -> ``findings_old_v3`` before
    recreating it. If a previous attempt was interrupted partway, the DB is
    left in a half-migrated state that would brick every subsequent open:
    either ``findings`` is already gone (the rename below would raise "no such
    table: findings") or a stale ``findings_old_v3`` lingers (the rename would
    raise "table findings_old_v3 already exists"). Normalise both states first
    so the migration is idempotent across interruptions and self-heals on the
    next open instead of failing permanently.
    """
    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if "findings_old_v3" in tables:
        if "findings" in tables:
            # Both present: a previous attempt recreated `findings` (possibly
            # empty or partial, if interrupted before/within the copy) without
            # dropping the original. findings_old_v3 holds the complete original
            # rows, so discard the partial copy and restore the original; the
            # rebuild below redoes the copy cleanly. Dropping the original here
            # instead would lose every finding when the new table was empty.
            conn.execute("DROP TABLE findings")
        # Interrupted after the rename, before the rebuild finished: restore the
        # original name so the rebuild runs against the complete data.
        conn.execute("ALTER TABLE findings_old_v3 RENAME TO findings")


def _invalidate_projection_checkpoint(conn: sqlite3.Connection) -> None:
    """Clear the projection checkpoint/size after the v3->v4 findings rebuild.

    Invalidating them forces the next ensure_projected call to treat the DB
    as "never projected" and trigger a full rebuild. The old schema's CHECK
    constraint silently dropped every ``major`` severity finding at insert
    time, so the existing rows are incomplete — the wider CHECK alone won't
    bring those findings back, but a fresh rebuild from events.jsonl will.

    We don't truncate the findings table here: the rebuild path
    (engine.rebuild) calls clear_all() before re-inserting, so doing it now
    would be redundant. Leaving the existing rows in place also keeps the
    migration non-destructive for callers that never trigger a re-read.

    run_meta may not exist on DBs upgraded from very old (v1/v2) schemas —
    the per-version upgrade scripts never created it, only the fresh-DB DDL
    does. Skip gracefully in that case; without a checkpoint, ensure_projected
    rebuilds from scratch anyway.
    """
    has_run_meta = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='run_meta'"
    ).fetchone() is not None
    if has_run_meta:
        conn.execute(
            "DELETE FROM run_meta WHERE key IN "
            "('projection_checkpoint', 'projection_event_log_size', 'actions_log_projected_size')"
        )


def _upgrade_v3_to_v4(conn: sqlite3.Connection) -> None:
    """Allow 'major' in the findings.severity CHECK constraint.

    The v3 schema's CHECK only permitted ``critical/high/medium/low/minor``.
    The scoring engine and event log emit ``major`` for the middle severity
    bucket, so ``INSERT OR IGNORE`` silently dropped every major finding —
    making principle scores look correct only as long as no critical was
    dismissed. After dismissing all criticals the score jumped to 10.0
    because the DB had no remaining violations.

    SQLite cannot ALTER a CHECK in place, so rebuild the table. Existing
    rows (all of which already pass the new, wider CHECK by construction)
    copy over unchanged, then the FTS5 index and triggers are recreated.

    Note: ``user_version`` is bumped by ``apply_evaluation_schema`` after
    this function returns.
    """
    _recover_v4_rebuild_state(conn)
    conn.executescript(_V4_REBUILD_DDL)
    _invalidate_projection_checkpoint(conn)


def _upgrade_v4_to_v5(conn: sqlite3.Connection) -> None:
    """Add exit_reason TEXT column to dimension_scores.

    Per-dim signal indicating why the subagent pool stopped (drained,
    time_limit, failure_streak, cancelled, error). NULL is interpreted
    as 'done' / drained by downstream consumers.

    dimension_scores may not exist on DBs upgraded from very old (v1/v2)
    schemas — only the fresh-DB DDL creates it, and the v1->v3 upgrade
    scripts never did. Skip the ALTER in that case; if a future caller
    needs the table they will get the fresh DDL on a new DB.
    """
    has_dim_scores = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dimension_scores'"
    ).fetchone() is not None
    if has_dim_scores:
        # Idempotency: the ALTER and the PRAGMA user_version bump in
        # apply_evaluation_schema commit separately (autocommit), so a crash
        # in between leaves the column added but the version still 4. Re-running
        # the bare ALTER would then raise "duplicate column name: exit_reason"
        # -- a plain OperationalError the scoring/dashboard read seams don't
        # catch, permanently bricking the run. Skip if the column already exists.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(dimension_scores)")}
        if "exit_reason" not in columns:
            conn.execute("ALTER TABLE dimension_scores ADD COLUMN exit_reason TEXT")


def _upgrade_v5_to_v6(conn: sqlite3.Connection) -> None:
    """Add the provenance_downgrade column to findings (default 0, issue #656).

    Marks findings the deterministic provenance gate (#639) de-escalated from
    critical to major so the SQL projection and dashboard can surface it.

    findings may not exist on DBs upgraded from very old (v1/v2) schemas that
    only ever created a subset of tables -- only the fresh-DB DDL guarantees
    it. Skip the ALTER in that case (mirrors the dimension_scores guard in
    _upgrade_v4_to_v5); a future caller needing the column gets the fresh DDL.

    Idempotency: the ALTER and the PRAGMA user_version bump in
    apply_evaluation_schema commit separately (autocommit), so a crash in
    between leaves the column added but the version still 5. Re-running the
    bare ALTER would then raise "duplicate column name: provenance_downgrade"
    -- a plain OperationalError the scoring/dashboard read seams don't catch,
    permanently bricking the run. Skip if the column already exists.
    """
    has_findings = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='findings'"
    ).fetchone() is not None
    if not has_findings:
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(findings)")}
    if "provenance_downgrade" not in columns:
        conn.execute(
            "ALTER TABLE findings ADD COLUMN provenance_downgrade INTEGER NOT NULL DEFAULT 0"
        )


def _upgrade_v6_to_v7(conn: sqlite3.Connection) -> None:
    """Add the scope_downgrade_json column to findings (default NULL).

    Marks findings the deterministic scope gate de-escalated from major to
    minor per the declared trust model, as a JSON-encoded {"rule", "from",
    "to"} dict (mirroring req_refs_json's shape) so the SQL projection and
    dashboard can surface WHICH rule waived the finding, not just that one
    did.

    findings may not exist on DBs upgraded from very old (v1/v2) schemas that
    only ever created a subset of tables -- only the fresh-DB DDL guarantees
    it. Skip the ALTER in that case (mirrors the provenance_downgrade guard
    in _upgrade_v5_to_v6); a future caller needing the column gets the fresh
    DDL.

    Idempotency: the ALTER and the PRAGMA user_version bump in
    apply_evaluation_schema commit separately (autocommit), so a crash in
    between leaves the column added but the version still 6. Re-running the
    bare ALTER would then raise "duplicate column name: scope_downgrade_json"
    -- a plain OperationalError the scoring/dashboard read seams don't catch,
    permanently bricking the run. Skip if the column already exists.
    """
    has_findings = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='findings'"
    ).fetchone() is not None
    if not has_findings:
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(findings)")}
    if "scope_downgrade_json" not in columns:
        conn.execute(
            "ALTER TABLE findings ADD COLUMN scope_downgrade_json TEXT"
        )


def _upgrade_v7_to_v8(conn: sqlite3.Connection) -> None:
    """Add the (requirement, file, line) composite index to findings.

    read_finding_details() (findings_queries.py) used to scan every row and
    filter matching keys in Python; the index lets its SQL WHERE seek
    instead. Skip if findings doesn't exist yet (mirrors the
    provenance_downgrade guard in _upgrade_v5_to_v6). IF NOT EXISTS makes a
    re-run safe if a crash landed the CREATE INDEX but not the later
    user_version bump (same idempotency shape as the other upgrades here).
    """
    has_findings = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='findings'"
    ).fetchone() is not None
    if not has_findings:
        return
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_req_file_line "
        "ON findings(requirement, file, line)"
    )


_UPGRADES = {
    1: _upgrade_v1_to_v2,
    2: _upgrade_v2_to_v3,
    3: _upgrade_v3_to_v4,
    4: _upgrade_v4_to_v5,
    5: _upgrade_v5_to_v6,
    6: _upgrade_v6_to_v7,
    7: _upgrade_v7_to_v8,
}


def apply_evaluation_schema(conn: sqlite3.Connection) -> None:
    version = _current_version(conn)
    if version == SCHEMA_VERSION:
        return
    if version > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"evaluation.db has schema version {version}, "
            f"this binary supports {SCHEMA_VERSION}",
        )
    if version == 0:
        # Fresh DB: apply the latest DDL (its leading PRAGMA sets user_version).
        conn.executescript(EVALUATION_DDL)
        return
    # Incremental upgrade path: walk N -> N+1 -> ... -> SCHEMA_VERSION.
    while version < SCHEMA_VERSION:
        upgrade = _UPGRADES.get(version)
        if upgrade is None:
            raise SchemaVersionError(
                f"missing upgrade path from schema version {version} "
                f"(target: {SCHEMA_VERSION})",
            )
        upgrade(conn)
        version += 1
        conn.execute(f"PRAGMA user_version = {version}")
