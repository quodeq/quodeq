"""Factory for creating rate-limit store instances."""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from quodeq.api._rate_limit_store import InMemoryRateLimitStore, RateLimitStore

_logger = logging.getLogger(__name__)

_KNOWN_BACKENDS = {"memory", "file"}
# Use the platform's temp dir (e.g. C:\Users\<user>\AppData\Local\Temp on
# Windows) instead of a hardcoded /tmp path that doesn't exist there.
_DEFAULT_RATE_LIMIT_FILE = str(Path(tempfile.gettempdir()) / "quodeq_rate_limits.json")


def _validated_rate_limit_path(raw: str) -> str:
    """Reject obviously-unsafe rate-limit file paths from the env.

    Falls back to the default if *raw* is empty, relative, or resolves to a
    location with parent-traversal components. Symlink resolution is
    deliberately not strict (the file may not exist yet on first run).
    """
    if not raw:
        return _DEFAULT_RATE_LIMIT_FILE
    try:
        candidate = Path(raw)
        if not candidate.is_absolute():
            raise ValueError("path must be absolute")
        resolved = candidate.resolve(strict=False)
        if ".." in resolved.parts:
            raise ValueError("path contains parent-directory traversal")
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
      ``quodeq_rate_limits.json`` in the platform temp dir).  Suitable for
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
