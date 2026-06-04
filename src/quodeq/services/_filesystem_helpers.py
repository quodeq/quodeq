"""Dimension helpers for the filesystem action provider."""
from __future__ import annotations

import functools
import json
import logging
from pathlib import Path

# NOTE: logging in inner layer — tracked for middleware extraction
_logger = logging.getLogger(__name__)

from quodeq.config.paths import default_paths


@functools.lru_cache(maxsize=4)
def _read_dimensions_from_file(dims_file: str) -> tuple[str, ...]:
    """Read dimension IDs from a dimensions.json file (cached by path)."""
    try:
        p = Path(dims_file)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            return tuple(d["id"] for d in data.get("applies", []))
        return ()
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return ()


class _DimensionsCache:
    """Explicit holder for the mutable dimensions cache (testable, no bare globals).

    Encapsulates a single ``value`` slot that caches the resolved dimension
    tuple.  Call :func:`reset_dimensions_cache` (or ``_dimensions_cache.reset()``)
    to clear cached state between tests or after configuration changes.
    """

    def __init__(self) -> None:
        self.value: tuple[str, ...] | None = None

    def reset(self) -> None:
        """Clear the cached dimensions, forcing a re-read on next access."""
        self.value = None


_dimensions_cache = _DimensionsCache()


def reset_dimensions_cache() -> None:
    """Reset the dimensions cache. Useful for test isolation."""
    _dimensions_cache.reset()


def _list_available_dimensions_for_discipline(paths: object | None = None) -> tuple[str, ...]:
    """Resolve available dimensions from universal dimensions.json (cached after first read).

    Pass *paths* to override the default path resolution (useful for testing).
    Returns a tuple (immutable) so the result is safe for caching.
    """
    if paths is None and _dimensions_cache.value is not None:
        return _dimensions_cache.value
    try:
        resolved = paths or default_paths()
        result = _read_dimensions_from_file(str(resolved.dimensions_file))
    except (OSError, TypeError) as exc:
        _logger.warning("Failed to load dimensions config: %s", exc)
        return ()
    if paths is None:
        _dimensions_cache.value = result
    return result
