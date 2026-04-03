"""Factory for creating rate-limit store instances."""
from __future__ import annotations

import logging
import os

from quodeq.api._rate_limit_store import InMemoryRateLimitStore, RateLimitStore

_logger = logging.getLogger(__name__)


def create_rate_limit_store(env: dict[str, str] | None = None) -> RateLimitStore:
    """Create the default rate-limit store.

    For multi-worker deployments, pass a ``RateLimitStore``-compatible
    shared backend (e.g. Redis) to ``create_app(rate_limit_store=...)``,
    or monkey-patch this factory.  Set ``QUODEQ_RATE_LIMIT_BACKEND`` to
    signal the desired backend (only ``memory`` is built-in).
    """
    backend = (env or os.environ).get("QUODEQ_RATE_LIMIT_BACKEND", "memory")
    if backend != "memory":
        _logger.warning(
            "Unknown rate-limit backend %r — falling back to in-memory. "
            "Pass a custom RateLimitStore to create_app() for shared backends.",
            backend,
        )
    return InMemoryRateLimitStore()
