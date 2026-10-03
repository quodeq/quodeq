"""The SQLite adapter's flavour of the boundary's unreadable-store error."""
from __future__ import annotations

import sqlite3

from quodeq.data.ports.errors import StoreUnreadableError


class SqliteStoreUnreadableError(StoreUnreadableError, sqlite3.DatabaseError):
    """An evaluation.db this binary cannot read: corrupt, or a newer schema.

    Descends from both the boundary error services catch and the driver
    error the adapter's own guards catch, so one raise satisfies both.
    """


def as_store_error(exc: sqlite3.DatabaseError) -> sqlite3.DatabaseError:
    """The boundary error for *exc* when it means "unreadable store".

    Corruption ("file is not a database", a malformed disk image) arrives
    as a bare ``sqlite3.DatabaseError``; that becomes the boundary error.
    Subclasses keep their meaning: a locked file or a constraint failure is
    not an unreadable store.
    """
    if type(exc) is sqlite3.DatabaseError:
        return SqliteStoreUnreadableError(str(exc))
    return exc
