from quodeq.adapters.web.http_client import HttpClient
from quodeq.ports.data_errors import AuthError, InvalidDataError, NotFoundError, ServerError


from quodeq.adapters.web.http_client import HttpResponse


def _check_response_status(response: HttpResponse) -> None:
    """Raise the appropriate error for non-success HTTP status codes."""
    if response.status in {401, 403}:
        raise AuthError("Authentication error")
    if response.status == 404:
        raise NotFoundError("Not found")
    if response.status >= 500:
        raise ServerError("Server error")


class WebEvaluatorsRepository:
    def __init__(self, base_url: str, client: HttpClient | None = None):
        self._base_url = base_url.rstrip("/")
        self._client = client or HttpClient()

    def list_evaluators(self, discipline: str) -> list[str]:
        response = self._client.get_json(f"{self._base_url}/evaluators/{discipline}", {})
        _check_response_status(response)
        if not isinstance(response.data, dict) or "dimensions" not in response.data or not isinstance(response.data["dimensions"], list):
            raise InvalidDataError("Invalid data format")
        return response.data["dimensions"]

    def get_evaluator(self, discipline: str, dimension_id: str) -> dict:
        response = self._client.get_json(f"{self._base_url}/evaluators/{discipline}/{dimension_id}", {})
        _check_response_status(response)
        if not isinstance(response.data, dict):
            raise InvalidDataError("Invalid data format")
        return response.data
