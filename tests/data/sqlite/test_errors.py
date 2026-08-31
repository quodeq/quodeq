"""StoreUnreadableError is the storage-agnostic alias services catch to mean
"this binary cannot read the state store" -- pin the alias identity so a
future refactor can't quietly drift it from sqlite3.DatabaseError.
"""
from __future__ import annotations

import sqlite3


def test_store_unreadable_error_is_sqlite_database_error():
    from quodeq.data.ports.errors import StoreUnreadableError

    assert StoreUnreadableError is sqlite3.DatabaseError


def test_schema_version_error_is_a_store_unreadable_error():
    from quodeq.data.ports.errors import StoreUnreadableError
    from quodeq.data.sqlite._migrations import SchemaVersionError

    assert issubclass(SchemaVersionError, StoreUnreadableError)
