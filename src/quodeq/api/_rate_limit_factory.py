"""Factory for creating rate-limit store instances."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from quodeq.api._rate_limit_config import default_rate_limit_path
from quodeq.api._rate_limit_store import InMemoryRateLimitStore, RateLimitStore

_logger = logging.getLogger(__name__)

_KNOWN_BACKENDS = {"memory", "file"}
_DEFAULT_RATE_LIMIT_FILE = str(default_rate_limit_path())


def _validated_rate_limit_path(raw: str) -> str:
    """Reject obviously-unsafe rate-limit file paths from the env.

    Falls back to the default if *raw* is empty, relative, resolves to a
    location with parent-traversal components, or is a symlink.
    """
    if not raw:
        return _DEFAULT_RATE_LIMIT_FILE
    try:
        candidate = Path(raw)
        if not candidate.is_absolute():
            raise ValueError("path must be absolute")
        if ".." in candidate.parts:
            raise ValueError("path contains parent-directory traversal")
        resolved = candidate.resolve(strict=False)
        # Defense in depth: FileRateLimitStore._save writes via os.replace,
        # which already defeats a symlink planted later. This rejects an
        # obviously-symlinked configured path early.
        if candidate.is_symlink():
            raise ValueError("path is a symlink")
    except (OSError, ValueError) as exc:
        _logger.warning(
            "Ignoring unsafe QUODEQ_RATE_LIMIT_FILE=%r (%s); using default %s",
            raw, exc, _DEFAULT_RATE_LIMIT_FILE,
        )
        return _DEFAULT_RATE_LIMIT_FILE
    return str(resolved)


def create_rate_limit_store(env: dict[str, str] | None = None) -> RateLimitStore:
    """Create the default rate-limit store.

    Set ``QUODEQ_RATE_LIMIT_BACKEND`` to choose a backend:

    - ``memory`` (default): process-local, no external dependencies.
    - ``file``: JSON file in ``QUODEQ_RATE_LIMIT_FILE`` (default:
      ``~/.quodeq/quodeq_rate_limits.json``).  Suitable for
      single-machine multi-worker setups but not recommended for
      high-throughput.

    For production multi-worker deployments, pass a ``RateLimitStore``-
    compatible shared backend (e.g. Redis) to
    ``create_app(rate_limit_store=...)``.
    """
    environ = env or os.environ
    backend = environ.get("QUODEQ_RATE_LIMIT_BACKEND", "memory")

    if backend == "file":
        from quodeq.api._rate_limit_file_store import FileRateLimitStore
        path = _validated_rate_limit_path(environ.get("QUODEQ_RATE_LIMIT_FILE", ""))
        _logger.info("Using file-based rate-limit store at %s", path)
        return FileRateLimitStore(path)

    if backend != "memory":
        _logger.warning(
            "Unknown rate-limit backend %r — falling back to in-memory. "
            "Pass a custom RateLimitStore to create_app() for shared backends.",
            backend,
        )
    return InMemoryRateLimitStore()
