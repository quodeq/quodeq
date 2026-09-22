"""Storage-agnostic error types for the services/data boundary.

``StoreUnreadableError`` is the name services catch to mean "this binary
cannot read the state store" -- SQLite adapters raise their native driver
errors, which already subclass it directly (``SchemaVersionError`` in
``data/sqlite/_migrations.py``), so no adapter has to know the alias
exists. Lives under ``data/ports`` rather than ``data/sqlite`` so
``services/ports.py`` (protocols-only) can import it: the boundary is the
interface contract, not any one adapter's implementation.
"""
from __future__ import annotations

import sqlite3

StoreUnreadableError = sqlite3.DatabaseError
