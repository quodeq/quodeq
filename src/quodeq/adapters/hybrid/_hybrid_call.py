from __future__ import annotations

from collections.abc import Callable
from typing import ParamSpec, TypeVar

from quodeq.ports.data_errors import InvalidDataError, NetworkError, ServerError

_P = ParamSpec("_P")
_R = TypeVar("_R")


def hybrid_call(primary: Callable[_P, _R], fallback: Callable[_P, _R], *args: _P.args, **kwargs: _P.kwargs) -> _R:
    """Try *primary*; on network/server/data errors, fall back to *fallback*."""
    try:
        return primary(*args, **kwargs)
    except (NetworkError, ServerError, InvalidDataError):
        return fallback(*args, **kwargs)
