"""Additive evaluation.db upgrades after the v3->v4 rebuild: each adds a
column or an index, guarded to be idempotent. The version walk itself is in
_migrations.py."""
from __future__ import annotations

import sqlite3

FINDINGS_TABLE = "findings"  # the table most upgrades extend


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    """True when the database has a table called *name*."""
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _add_findings_column(conn: sqlite3.Connection, column: str, decl: str) -> None:
    """Add *column* (``ALTER TABLE findings ADD COLUMN <column> <decl>``) if it is missing.

    Two guards, both of which every additive findings upgrade needs:

    findings may not exist on DBs upgraded from very old (v1/v2) schemas that
    only ever created a subset of tables -- only the fresh-DB DDL guarantees
    it. The ALTER is skipped in that case (mirrors the dimension_scores guard
    in _upgrade_v4_to_v5); a future caller needing the column gets the fresh
    DDL.

    Idempotency: the ALTER and the PRAGMA user_version bump in
    apply_evaluation_schema commit separately (autocommit), so a crash in
    between leaves the column added but the version unbumped. Re-running the
    bare ALTER would then raise "duplicate column name: ..." -- a plain
    OperationalError the scoring/dashboard read seams don't catch, permanently
    bricking the run. Skip if the column already exists.
    """
    if table_exists(conn, FINDINGS_TABLE):
        add_missing_column(conn, FINDINGS_TABLE, column, decl)


def add_missing_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    """``ALTER TABLE <table> ADD COLUMN <column> <decl>`` unless *table* already has *column*.

    The caller checks that *table* exists where it may not. *table*, *column*
    and *decl* are migration literals, never input.
    """
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def upgrade_v5_to_v6(conn: sqlite3.Connection) -> None:
    """Add the provenance_downgrade column to findings (default 0, issue #656).

    Marks findings the deterministic provenance gate (#639) de-escalated from
    critical to major so the SQL projection and dashboard can surface it.

    Guards and idempotency: see :func:`_add_findings_column`.
    """
    _add_findings_column(conn, "provenance_downgrade", "INTEGER NOT NULL DEFAULT 0")


def upgrade_v6_to_v7(conn: sqlite3.Connection) -> None:
    """Add the scope_downgrade_json column to findings (default NULL).

    Marks findings the deterministic scope gate de-escalated from major to
    minor per the declared trust model, as a JSON-encoded {"rule", "from",
    "to"} dict (mirroring req_refs_json's shape) so the SQL projection and
    dashboard can surface WHICH rule waived the finding, not just that one
    did.

    Guards and idempotency: see :func:`_add_findings_column`.
    """
    _add_findings_column(conn, "scope_downgrade_json", "TEXT")


def upgrade_v7_to_v8(conn: sqlite3.Connection) -> None:
    """Add the (requirement, file, line) composite index to findings.

    read_finding_details() (findings_queries.py) used to scan every row and
    filter matching keys in Python; the index lets its SQL WHERE seek
    instead. Skip if findings doesn't exist yet (mirrors the
    provenance_downgrade guard in upgrade_v5_to_v6). IF NOT EXISTS makes a
    re-run safe if a crash landed the CREATE INDEX but not the later
    user_version bump (same idempotency shape as the other upgrades here).
    """
    if not table_exists(conn, FINDINGS_TABLE):
        return
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_req_file_line "
        "ON findings(requirement, file, line)"
    )


def upgrade_v8_to_v9(conn: sqlite3.Connection) -> None:
    """Add the violation_type_raw column to findings (default '').

    Stores the model's violation-type tag as emitted so the taxonomy report
    can list unmapped tags per requirement.

    Guards and idempotency: see :func:`_add_findings_column`.
    """
    _add_findings_column(conn, "violation_type_raw", "TEXT NOT NULL DEFAULT ''")
