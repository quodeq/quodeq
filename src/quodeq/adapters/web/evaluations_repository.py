"""Web API-backed repository for evaluation reports."""
from __future__ import annotations

from urllib.parse import quote

from quodeq.adapters.web.base_repository import WebRepository


class WebEvaluationsRepository(WebRepository):
    """Fetch evaluation report data from a remote HTTP API."""

    def list_reports(self) -> list[str]:
        """Retrieve all report IDs from the remote API."""
        return self._get_list("/reports", "reports")

    def get_report(self, report_id: str) -> dict:
        """Fetch a single evaluation report by ID from the remote API."""
        return self._get_dict(f"/reports/{quote(report_id, safe='')}")
