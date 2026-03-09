"""Minimal HTTP client for JSON API communication."""

from dataclasses import dataclass
import json
from urllib import request

from quodeq.ports.data_errors import AuthError, NotFoundError, ServerError


@dataclass(frozen=True)
class HttpResponse:
    """Immutable container for an HTTP status code and parsed JSON payload."""

    status: int
    data: dict


def check_response_status(response: HttpResponse) -> None:
    """Raise the appropriate error for non-success HTTP status codes."""
    if response.status in {401, 403}:
        raise AuthError("Authentication error")
    if response.status == 404:
        raise NotFoundError("Not found")
    if response.status >= 500:
        raise ServerError("Server error")


class HttpClient:
    """Simple HTTP client that performs GET requests and returns parsed JSON."""

    def get_json(self, url: str, headers: dict[str, str]) -> HttpResponse:
        """Send a GET request to the URL and return the parsed JSON response."""
        req = request.Request(url, headers=headers)
        try:
            with request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                return HttpResponse(resp.status, payload)
        except request.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8")) if exc.fp else {"error": "http error"}
            return HttpResponse(exc.code, payload)
