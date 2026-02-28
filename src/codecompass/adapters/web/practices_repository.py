from codecompass.adapters.web.http_client import HttpClient, HttpResponse
from codecompass.ports.data_errors import AuthError, InvalidDataError, NotFoundError, ServerError


class WebPracticesRepository:
    def __init__(self, base_url: str, client: HttpClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or HttpClient()

    def list_topics(self, discipline: str) -> list[str]:
        resp = self._client.get_json(f"{self._base_url}/practices/{discipline}", headers={})
        return _extract_topics(resp)

    def get_practice(self, discipline: str, topic: str) -> dict:
        resp = self._client.get_json(f"{self._base_url}/practices/{discipline}/{topic}", headers={})
        return _extract_payload(resp)


def _extract_topics(resp: HttpResponse) -> list[str]:
    payload = _extract_payload(resp)
    topics = payload.get("topics")
    if not isinstance(topics, list):
        raise InvalidDataError("Expected topics list")
    return [str(item) for item in topics]


def _extract_payload(resp: HttpResponse) -> dict:
    if resp.status in {401, 403}:
        raise AuthError("Unauthorized")
    if resp.status == 404:
        raise NotFoundError("Not found")
    if resp.status >= 500:
        raise ServerError("Server error")
    if not isinstance(resp.data, dict):
        raise InvalidDataError("Invalid JSON payload")
    return resp.data
