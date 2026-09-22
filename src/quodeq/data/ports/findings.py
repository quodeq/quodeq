"""Repository protocol for findings persistence."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol, runtime_checkable

from quodeq.core.types.finding import Finding


@runtime_checkable
class FindingsRepository(Protocol):
    """Persistence boundary for individual findings within a single run."""

    def insert_finding(self, finding: dict[str, Any]) -> bool:
        """Insert a finding (FindingsRouter wire-dict shape).

        Returns True if inserted, False if a duplicate (same dedup key) was ignored.
        """
        ...

    def list_by_dimension(self, dimension: str) -> list[Finding]:
        """Return all findings for a dimension."""
        ...

    def list_all(self) -> list[Finding]:
        """Return every finding regardless of dimension, in insertion order."""
        ...

    def count_by_dimension(self) -> dict[str, int]:
        """Return total finding counts grouped by dimension."""
        ...

    def search(self, query: str, limit: int = 100, *,
               exclude_dimensions: Iterable[str] | None = None) -> list[Finding]:
        """FTS5 search across reason and snippet.

        ``exclude_dimensions`` drops whole dimensions from the result BEFORE
        the limit is applied (case-insensitive match on the stored dimension).
        """
        ...

    def set_verdict(self, *, practice_id: str, file: str, line: int, verdict: str) -> int:
        """Update verdict for findings matching (practice_id, file, line).

        Updates ALL findings matching the tuple — multiple rows with the
        same (practice_id, file, line) but different titles or snippets
        will all receive the new verdict. The caller can detect this from
        the returned rows-affected count. Use this for dismiss/restore flows.
        """
        ...
