"""Additive evaluation.db upgrades after the v3->v4 rebuild: each adds a
column or an index, guarded to be idempotent. Split out of _migrations.py to
keep both files under the size ratchet; the version walk itself stays in
_migrations.py."""
from __future__ import annotations

import sqlite3


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


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
    if not _table_exists(conn, "findings"):
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
    if not _table_exists(conn, "findings"):
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
    if not _table_exists(conn, "findings"):
        return
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_req_file_line "
        "ON findings(requirement, file, line)"
    )


def _upgrade_v8_to_v9(conn: sqlite3.Connection) -> None:
    """Add the violation_type_raw column to findings (default '').

    Stores the model's violation-type tag as emitted so the taxonomy report
    can list unmapped tags per requirement. Skip when findings does not
    exist (very old DBs, mirrors _upgrade_v5_to_v6) and when the column is
    already present: the ALTER and the user_version bump commit separately,
    so a crash between them must not brick the run on re-run.
    """
    if not _table_exists(conn, "findings"):
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(findings)")}
    if "violation_type_raw" not in columns:
        conn.execute(
            "ALTER TABLE findings ADD COLUMN violation_type_raw TEXT NOT NULL DEFAULT ''"
        )
