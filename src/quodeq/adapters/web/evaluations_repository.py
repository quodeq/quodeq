from quodeq.adapters.web.http_client import HttpClient, check_response_status
from quodeq.ports.data_errors import InvalidDataError


class WebEvaluationsRepository:
    def __init__(self, base_url: str, client: HttpClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.client = client or HttpClient()

    def list_reports(self) -> list[str]:
        response = self.client.get_json(f"{self.base_url}/reports", {})
        check_response_status(response)
        if not isinstance(response.data, dict) or "reports" not in response.data or not isinstance(response.data["reports"], list):
            raise InvalidDataError("Invalid data format")
        return response.data["reports"]

    def get_report(self, report_id: str) -> dict:
        response = self.client.get_json(f"{self.base_url}/reports/{report_id}", {})
        check_response_status(response)
        if not isinstance(response.data, dict):
            raise InvalidDataError("Invalid data format")
        return response.data
