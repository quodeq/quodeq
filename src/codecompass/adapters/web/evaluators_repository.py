from codecompass.adapters.web.http_client import HttpClient
from codecompass.ports.data_errors import AuthError, InvalidDataError, NotFoundError, ServerError


class WebEvaluatorsRepository:
    def __init__(self, base_url: str, client: HttpClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.client = client or HttpClient()

    def list_evaluators(self, discipline: str) -> list[str]:
        response = self.client.get_json(f"{self.base_url}/evaluators/{discipline}", {})
        if response.status in {401, 403}:
            raise AuthError("Authentication error")
        elif response.status == 404:
            raise NotFoundError("Not found")
        elif response.status >= 500:
            raise ServerError("Server error")
        if not isinstance(response.data, dict) or "dimensions" not in response.data or not isinstance(response.data["dimensions"], list):
            raise InvalidDataError("Invalid data format")
        return response.data["dimensions"]

    def get_evaluator(self, discipline: str, dimension_id: str) -> dict:
        response = self.client.get_json(f"{self.base_url}/evaluators/{discipline}/{dimension_id}", {})
        if response.status in {401, 403}:
            raise AuthError("Authentication error")
        elif response.status == 404:
            raise NotFoundError("Not found")
        elif response.status >= 500:
            raise ServerError("Server error")
        if not isinstance(response.data, dict):
            raise InvalidDataError("Invalid data format")
        return response.data
