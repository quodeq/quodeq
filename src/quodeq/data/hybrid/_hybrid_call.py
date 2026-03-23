from __future__ import annotations

import logging
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from quodeq.data.ports.data_errors import InvalidDataError, NetworkError, ServerError

_logger = logging.getLogger(__name__)

_P = ParamSpec("_P")
_R = TypeVar("_R")


def hybrid_call(primary: Callable[_P, _R], fallback: Callable[_P, _R], *args: _P.args, **kwargs: _P.kwargs) -> _R:
    """Try *primary*; on network/server/data errors, fall back to *fallback*.

    Example::

        result = hybrid_call(web_repo.list_items, fs_repo.list_items)
    """
    try:
        return primary(*args, **kwargs)
    except (NetworkError, ServerError, InvalidDataError) as exc:
        _logger.warning("Primary call failed, falling back: %s", exc)
        return fallback(*args, **kwargs)
