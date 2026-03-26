from __future__ import annotations

import logging
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from quodeq.data.ports.data_errors import InvalidDataError, NetworkError, ServerError

_logger = logging.getLogger(__name__)

_P = ParamSpec("_P")
_R = TypeVar("_R")


def hybrid_call(primary: Callable[_P, _R], fallback: Callable[_P, _R], *args: _P.args, **kwargs: _P.kwargs) -> _R:
    """Try *primary* (with one retry); on persistent failure, fall back to *fallback*.

    Example::

        result = hybrid_call(web_repo.list_items, fs_repo.list_items)
    """
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            return primary(*args, **kwargs)
        except (NetworkError, ServerError, InvalidDataError) as exc:
            last_exc = exc
            if attempt == 0:
                _logger.debug("Primary call failed (attempt 1), retrying: %s", exc)
    _logger.warning("Primary call failed after retry, falling back: %s", last_exc)
    return fallback(*args, **kwargs)
