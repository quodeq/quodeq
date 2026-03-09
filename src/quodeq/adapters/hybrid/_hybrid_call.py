from __future__ import annotations

from typing import Any, Callable

from quodeq.ports.data_errors import InvalidDataError, NetworkError, ServerError


def hybrid_call(primary: Callable[..., Any], fallback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Try *primary*; on network/server/data errors, fall back to *fallback*."""
    try:
        return primary(*args, **kwargs)
    except (NetworkError, ServerError, InvalidDataError):
        return fallback(*args, **kwargs)
