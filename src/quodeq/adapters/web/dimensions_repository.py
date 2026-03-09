"""Web API-backed repository for quality dimension definitions."""

from quodeq.adapters.web.http_client import HttpClient, check_response_status
from quodeq.ports.data_errors import InvalidDataError


class WebDimensionsRepository:
    """Fetch dimension data from a remote HTTP API."""

    def __init__(self, base_url: str, client: HttpClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.client = client or HttpClient()

    def list_dimensions(self) -> list[str]:
        """Retrieve all dimension names from the remote API."""
        response = self.client.get_json(f"{self.base_url}/dimensions", {})
        check_response_status(response)
        if not isinstance(response.data, dict) or "dimensions" not in response.data or not isinstance(response.data["dimensions"], list):
            raise InvalidDataError("Invalid data format")
        return response.data["dimensions"]

    def get_dimension(self, dimension_id: str) -> dict:
        """Fetch a single dimension definition by ID from the remote API."""
        response = self.client.get_json(f"{self.base_url}/dimensions/{dimension_id}", {})
        check_response_status(response)
        if not isinstance(response.data, dict):
            raise InvalidDataError("Invalid data format")
        return response.data
