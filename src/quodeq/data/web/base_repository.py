"""Base class for web API-backed repositories."""
from __future__ import annotations

from quodeq.data.web.http_client import HttpClient, check_response_status
from quodeq.data.ports.data_errors import InvalidDataError


class WebRepository:
    """Common initialisation and helper methods for web repositories."""

    def __init__(self, base_url: str, client: HttpClient | None = None):
        self._base_url = base_url.rstrip("/")
        self._client = client or HttpClient()

    def _get_dict(self, path: str) -> dict[str, object]:
        """GET *path*, validate the response is a dict, and return it."""
        response = self._client.get_json(f"{self._base_url}{path}", {})
        check_response_status(response)
        if not isinstance(response.data, dict):
            raise InvalidDataError(
                "Invalid data format: expected a JSON object with 'data' key. "
                "Verify the API endpoint URL and authentication."
            )
        return response.data

    def _get_list(self, path: str, key: str) -> list[object]:
        """GET *path*, validate response contains a list at *key*, and return it."""
        data = self._get_dict(path)
        if key not in data or not isinstance(data[key], list):
            raise InvalidDataError(
                f"Invalid data format: expected '{key}' to be a list. "
                f"Verify the API response structure and that the endpoint is returning the correct data."
            )
        return data[key]
