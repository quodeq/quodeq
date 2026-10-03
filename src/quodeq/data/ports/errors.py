"""Storage-agnostic error types for the services/data boundary.

``StoreUnreadableError`` is the name services catch to mean "this binary
cannot read the state store". It is a plain exception with no driver
ancestry: each adapter raises its own subclass (the SQLite one also
descends from ``sqlite3.DatabaseError`` so driver-level guards keep
working), and services never name a driver type. Lives under
``data/ports`` rather than ``data/sqlite`` so ``services/ports.py``
(protocols-only) can import it: the boundary is the interface contract,
not any one adapter's implementation.
"""
from __future__ import annotations


class StoreUnreadableError(Exception):
    """The state store exists but this binary cannot read it."""
