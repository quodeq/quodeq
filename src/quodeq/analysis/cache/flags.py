"""Feature flags and kill switches for the result cache."""
from __future__ import annotations

import os

_V2_ENV = "QUODEQ_CACHE_V2"
_DISABLE_ENV = "QUODEQ_DISABLE_RESULT_CACHE"


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def is_cache_v2_enabled() -> bool:
    """True when callers should consult the result cache.

    Phase B opt-in. When the migration completes the flag flips default-on
    and is eventually deleted alongside the legacy incremental path.
    """
    return _truthy(_V2_ENV)


def is_result_cache_disabled() -> bool:
    """Kill switch — bypass the cache entirely (mirrors online_cache pattern)."""
    return _truthy(_DISABLE_ENV)
