from quodeq.ports.data_errors import InvalidDataError, NetworkError, ServerError


class HybridEvaluationsRepository:
    def __init__(self, web, fs) -> None:
        self._web = web
        self._fs = fs

    def list_reports(self) -> list[str]:
        try:
            return self._web.list_reports()
        except (NetworkError, ServerError, InvalidDataError):
            return self._fs.list_reports()

    def get_report(self, report_id: str) -> dict:
        try:
            return self._web.get_report(report_id)
        except (NetworkError, ServerError, InvalidDataError):
            return self._fs.get_report(report_id)
