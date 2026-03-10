from __future__ import annotations

from typing import Protocol


class EvaluationsRepository(Protocol):
    """Repository for accessing stored evaluation reports."""

    def list_reports(self) -> list[str]:
        """Return identifiers for all available evaluation reports."""
        ...

    def get_report(self, report_id: str) -> dict:
        """Return the full report data for a given report identifier."""
        ...
