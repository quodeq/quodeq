"""HTTP response container and status-checking logic."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus

from quodeq.data.ports.data_errors import AuthError, NotFoundError, ServerError


@dataclass(frozen=True)
class HttpResponse:
    """Immutable container for an HTTP status code and parsed JSON payload."""

    status: int
    data: dict


def check_response_status(response: HttpResponse) -> None:
    """Raise the appropriate error for non-success HTTP status codes.

    Errors are raised with generic messages only.  Callers MUST NOT
    surface ``response.data`` to end users — it may contain upstream
    error details that should remain internal.
    """
    if response.status in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
        raise AuthError("Authentication error — verify your API key is valid and not expired")
    if response.status == HTTPStatus.NOT_FOUND:
        raise NotFoundError("Resource not found — verify the URL and that the resource exists")
    if response.status >= HTTPStatus.INTERNAL_SERVER_ERROR:
        raise ServerError("Server error")
