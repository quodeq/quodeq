"""Sanity checks on schema DDL strings."""
from quodeq.data.sqlite import _schema


def test_evaluation_ddl_creates_findings_table():
    assert "CREATE TABLE findings" in _schema.EVALUATION_DDL
    assert "CHECK (verdict IN ('violation','compliance','dismissed'))" in _schema.EVALUATION_DDL


def test_evaluation_ddl_includes_fts5():
    assert "USING fts5" in _schema.EVALUATION_DDL
    assert "content='findings'" in _schema.EVALUATION_DDL


def test_evaluation_ddl_sets_user_version_1():
    assert "PRAGMA user_version = 1" in _schema.EVALUATION_DDL
