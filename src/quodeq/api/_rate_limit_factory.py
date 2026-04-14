"""Factory for creating rate-limit store instances."""
from __future__ import annotations

import logging
import os

from quodeq.api._rate_limit_store import InMemoryRateLimitStore, RateLimitStore

_logger = logging.getLogger(__name__)

_KNOWN_BACKENDS = {"memory", "file"}


def create_rate_limit_store(env: dict[str, str] | None = None) -> RateLimitStore:
    """Create the default rate-limit store.

    Set ``QUODEQ_RATE_LIMIT_BACKEND`` to choose a backend:

    - ``memory`` (default): process-local, no external dependencies.
    - ``file``: JSON file in ``QUODEQ_RATE_LIMIT_FILE`` (default
      ``/tmp/quodeq_rate_limits.json``).  Suitable for single-machine
      multi-worker setups but not recommended for high-throughput.

    For production multi-worker deployments, pass a ``RateLimitStore``-
    compatible shared backend (e.g. Redis) to
    ``create_app(rate_limit_store=...)``.
    """
    environ = env or os.environ
    backend = environ.get("QUODEQ_RATE_LIMIT_BACKEND", "memory")

    if backend == "file":
        from quodeq.api._rate_limit_file_store import FileRateLimitStore
        path = environ.get("QUODEQ_RATE_LIMIT_FILE", "/tmp/quodeq_rate_limits.json")
        _logger.info("Using file-based rate-limit store at %s", path)
        return FileRateLimitStore(path)

    if backend != "memory":
        _logger.warning(
            "Unknown rate-limit backend %r — falling back to in-memory. "
            "Pass a custom RateLimitStore to create_app() for shared backends.",
            backend,
        )
    return InMemoryRateLimitStore()
