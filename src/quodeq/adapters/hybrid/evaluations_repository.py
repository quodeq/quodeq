"""Hybrid repository that tries the web adapter first, falling back to filesystem."""

from quodeq.adapters.hybrid._hybrid_call import hybrid_call


class HybridEvaluationsRepository:
    """Evaluations repository that delegates to web then falls back to filesystem."""

    def __init__(self, web, fs) -> None:
        self._web = web
        self._fs = fs

    def list_reports(self) -> list[str]:
        """Return all report IDs, preferring the web source."""
        return hybrid_call(self._web.list_reports, self._fs.list_reports)

    def get_report(self, report_id: str) -> dict:
        """Fetch a single evaluation report, preferring the web source."""
        return hybrid_call(self._web.get_report, self._fs.get_report, report_id)
