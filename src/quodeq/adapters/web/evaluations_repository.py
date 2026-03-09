from quodeq.adapters.web.http_client import HttpClient
from quodeq.ports.data_errors import AuthError, InvalidDataError, NotFoundError, ServerError


class WebEvaluationsRepository:
    def __init__(self, base_url: str, client: HttpClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.client = client or HttpClient()

    def list_reports(self) -> list[str]:
        response = self.client.get_json(f"{self.base_url}/reports", {})
        if response.status in {401, 403}:
            raise AuthError("Authentication error")
        elif response.status == 404:
            raise NotFoundError("Not found")
        elif response.status >= 500:
            raise ServerError("Server error")
        if not isinstance(response.data, dict) or "reports" not in response.data or not isinstance(response.data["reports"], list):
            raise InvalidDataError("Invalid data format")
        return response.data["reports"]

    def get_report(self, report_id: str) -> dict:
        response = self.client.get_json(f"{self.base_url}/reports/{report_id}", {})
        if response.status in {401, 403}:
            raise AuthError("Authentication error")
        elif response.status == 404:
            raise NotFoundError("Not found")
        elif response.status >= 500:
            raise ServerError("Server error")
        if not isinstance(response.data, dict):
            raise InvalidDataError("Invalid data format")
        return response.data
