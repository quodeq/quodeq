"""Read seam for previously-dismissed findings, consumed by precedent matching."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

DismissedSnippetsReader = Callable[[Path], Iterable[tuple[str | None, str | None]]]
"""Reads ``(requirement, snippet)`` pairs for every dismissed finding under a
run directory.

Mirrors the public surface of
``quodeq.data.sqlite.findings_queries.read_dismissed_snippets``; consumers
type against this alias so a fake reader can stand in for isolated tests
without importing the sqlite layer.
"""
