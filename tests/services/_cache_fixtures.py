"""Shared DimensionResult / cache-context builders for tests/services/test_cache*.py."""
from __future__ import annotations

import threading
from collections import OrderedDict

from quodeq.core.types import DimensionResult
from quodeq.services.cache import DimensionCacheContext


def _make_dim(name: str = "security") -> DimensionResult:
    return DimensionResult(dimension=name)


def _make_ctx(max_size: int = 10) -> DimensionCacheContext:
    return DimensionCacheContext(
        cache=OrderedDict(),
        lock=threading.Lock(),
        max_size=max_size,
    )
