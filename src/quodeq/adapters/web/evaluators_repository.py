"""Web API-backed repository for evaluator configuration files."""

from quodeq.adapters.web.http_client import HttpClient, check_response_status
from quodeq.ports.data_errors import InvalidDataError


class WebEvaluatorsRepository:
    """Fetch evaluator definitions from a remote HTTP API."""

    def __init__(self, base_url: str, client: HttpClient | None = None):
        self._base_url = base_url.rstrip("/")
        self._client = client or HttpClient()

    def list_evaluators(self, discipline: str) -> list[str]:
        """Retrieve all evaluator names for a discipline from the remote API."""
        response = self._client.get_json(f"{self._base_url}/evaluators/{discipline}", {})
        check_response_status(response)
        if not isinstance(response.data, dict) or "dimensions" not in response.data or not isinstance(response.data["dimensions"], list):
            raise InvalidDataError("Invalid data format")
        return response.data["dimensions"]

    def get_evaluator(self, discipline: str, dimension_id: str) -> dict:
        """Fetch a single evaluator definition by discipline and dimension from the remote API."""
        response = self._client.get_json(f"{self._base_url}/evaluators/{discipline}/{dimension_id}", {})
        check_response_status(response)
        if not isinstance(response.data, dict):
            raise InvalidDataError("Invalid data format")
        return response.data
