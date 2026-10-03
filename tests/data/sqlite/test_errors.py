"""StoreUnreadableError is the storage-agnostic error services catch to mean
"this binary cannot read the state store": a plain exception the SQLite
adapter's own error descends from, never a driver type itself.

The adapter translates bare driver corruption errors into its flavour at
the connection boundary; driver subclasses with their own meaning (a
locked file, a constraint failure) pass through untouched.
"""
from __future__ import annotations

import sqlite3

import pytest

from quodeq.data.ports.errors import StoreUnreadableError
from quodeq.data.sqlite.connection import open_evaluation_db
from quodeq.data.sqlite.errors import SqliteStoreUnreadableError, as_store_error
from quodeq.data.sqlite._migrations import SchemaVersionError


def test_store_unreadable_error_names_no_driver():
    assert issubclass(StoreUnreadableError, Exception)
    assert not issubclass(StoreUnreadableError, sqlite3.Error)


def test_sqlite_flavour_is_both_boundary_and_driver_error():
    assert issubclass(SqliteStoreUnreadableError, StoreUnreadableError)
    assert issubclass(SqliteStoreUnreadableError, sqlite3.DatabaseError)


def test_schema_version_error_is_a_store_unreadable_error():
    assert issubclass(SchemaVersionError, StoreUnreadableError)


def test_bare_database_error_becomes_the_boundary_error():
    translated = as_store_error(sqlite3.DatabaseError("file is not a database"))
    assert isinstance(translated, StoreUnreadableError)
    assert str(translated) == "file is not a database"


@pytest.mark.parametrize("exc", [sqlite3.OperationalError("locked"), sqlite3.IntegrityError("unique")])
def test_driver_subclasses_keep_their_meaning(exc):
    assert as_store_error(exc) is exc


def test_corrupt_file_surfaces_as_store_unreadable(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "evaluation.db").write_bytes(b"this is not a sqlite file, just bytes " * 40)
    with pytest.raises(StoreUnreadableError):
        with open_evaluation_db(run_dir):
            pass


def test_corruption_seen_on_first_query_surfaces_as_store_unreadable(tmp_path):
    with pytest.raises(StoreUnreadableError):
        with open_evaluation_db(tmp_path / "run") as conn:
            raise sqlite3.DatabaseError("database disk image is malformed")
    with pytest.raises(sqlite3.OperationalError):
        with open_evaluation_db(tmp_path / "run2") as conn:
            conn.execute("select * from no_such_table")
