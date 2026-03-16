"""Re-export shim — canonical location is quodeq.data.web.http_client."""
from quodeq.data.web.http_client import (
    HttpClient,
    HttpClientConfig,
    HttpResponse,
    check_response_status,
)

__all__ = [
    "HttpClient",
    "HttpClientConfig",
    "HttpResponse",
    "check_response_status",
]
