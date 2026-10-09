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

    read_finding_details() (findings_queries.py) filters on those keys in its
    SQL WHERE; the index lets that seek instead of scanning every row. Skip if findings doesn't exist yet (mirrors the
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


_MOVE_BLANK_PRINCIPLES_SQL = """
INSERT OR IGNORE INTO unmapped_findings (
    dimension, requirement, principle_hint, verdict, severity, file, line,
    title, reason, snippet, unmapped_reason, dedup_key
)
SELECT dimension, requirement, '', verdict, severity, file, line,
       title, reason, snippet, 'missing_principle', dedup_key
FROM findings WHERE practice_id = '';
DELETE FROM findings WHERE practice_id = '';
"""


def upgrade_v9_to_v10(conn: sqlite3.Connection) -> None:
    """Add ``unmapped_findings`` and the triggers that keep ``findings`` placed.

    Rows already stored with an empty principle move to ``unmapped_findings``
    rather than being deleted; the run's missing standard stamp then
    re-projects it from its events, which places them through admission.
    A DB without a ``findings`` table (very old schemas) only gets the new
    table. Every statement is idempotent, so a crash before the version bump
    is safe to re-run.
    """
    from quodeq.data.sqlite._schema import PRINCIPLE_TRIGGERS_DDL, UNMAPPED_TABLE_DDL  # noqa: PLC0415

    conn.executescript(UNMAPPED_TABLE_DDL)
    if table_exists(conn, FINDINGS_TABLE):
        conn.executescript(_MOVE_BLANK_PRINCIPLES_SQL)
        conn.executescript(PRINCIPLE_TRIGGERS_DDL)


def upgrade_v10_to_v11(conn: sqlite3.Connection) -> None:
    """Add ``confidence`` to principle_grades: the thin-evidence marker that replaced the
    Insufficient gate (grade algorithm 4). Idempotent; a DB without the table only gets
    the fresh DDL later."""
    if table_exists(conn, "principle_grades"):
        add_missing_column(conn, "principle_grades", "confidence", "TEXT")
