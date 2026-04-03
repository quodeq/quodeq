"""Rate-limit store abstractions for the Quodeq API.

This module re-exports from focused sub-modules for backward compatibility.
"""
from quodeq.api._rate_limit_config import (  # noqa: F401
    _DEFAULT_RATE_LIMIT_MAX,
    _DEFAULT_RATE_LIMIT_WINDOW,
    _PRUNE_THRESHOLD_MULTIPLIER,
    _RATE_STORE_MAX_IPS,
    _rate_limit_max,
    _rate_limit_window,
)
from quodeq.api._rate_limit_factory import create_rate_limit_store  # noqa: F401
from quodeq.api._rate_limit_store import (  # noqa: F401
    InMemoryRateLimitStore,
    RateLimitStore,
)
