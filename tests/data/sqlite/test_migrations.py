import sqlite3
import pytest
from quodeq.data.sqlite._migrations import (
    apply_evaluation_schema,
    apply_index_schema,
    SchemaVersionError,
)


def test_apply_evaluation_schema_on_fresh_db_sets_version():
    conn = sqlite3.connect(":memory:")
    apply_evaluation_schema(conn)
    cur = conn.execute("PRAGMA user_version")
    assert cur.fetchone()[0] == 1


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
    assert cur.fetchone()[0] == 1


def test_apply_evaluation_schema_rejects_newer_version():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA user_version = 99")
    with pytest.raises(SchemaVersionError):
        apply_evaluation_schema(conn)


def test_apply_index_schema_creates_runs_table():
    conn = sqlite3.connect(":memory:")
    apply_index_schema(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "runs" in tables
