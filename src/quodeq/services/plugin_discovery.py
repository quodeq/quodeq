"""Discover available languages and return plugin metadata."""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from quodeq.core.types import PluginDimension, PluginInfo
from quodeq.config.paths import default_paths
from quodeq.shared.utils import read_json

_logger = logging.getLogger(__name__)

_PLUGIN_CACHE_TTL = 60  # seconds; allows runtime plugin changes to propagate


class _PluginCache:
    """Thread-safe TTL cache for plugin metadata."""

    def __init__(self, ttl: float = _PLUGIN_CACHE_TTL) -> None:
        self._lock = threading.Lock()
        self._cache: list[PluginInfo] | None = None
        self._ts: float = 0.0
        self._ttl = ttl

    def get(self) -> list[PluginInfo] | None:
        with self._lock:
            if self._cache is not None and time.monotonic() - self._ts < self._ttl:
                return self._cache
        return None

    def set(self, data: list[PluginInfo]) -> None:
        with self._lock:
            self._cache = data
            self._ts = time.monotonic()


# Module-level singleton for plugin metadata caching (TTL-based).
# Thread-safe via internal locking.  Override by passing *cache* to
# discover_plugins() for testing or alternative backends.
_plugin_cache = _PluginCache()


def _discover_from_detection(detection_file: Path, dimensions_file: Path) -> list[PluginInfo]:
    """Build plugin info from universal detection.json + dimensions.json."""
    detection = read_json(detection_file)
    ext_map: dict[str, str] = detection.get("extensions", {})

    # Group extensions by language
    lang_extensions: dict[str, list[str]] = {}
    for ext, lang in ext_map.items():
        lang_extensions.setdefault(lang, []).append(ext)

    # Load universal dimensions
    dims: list[PluginDimension] = []
    try:
        dims_data = read_json(dimensions_file)
        dims = [
            PluginDimension(id=d["id"], weight=d.get("weight", 1), iso_25010=d.get("iso_25010"))
            for d in dims_data.get("applies", [])
        ]
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        _logger.warning("Failed to parse dimensions.json: %s", exc)

    result: list[PluginInfo] = []
    for lang, exts in sorted(lang_extensions.items()):
        result.append(PluginInfo(
            id=lang,
            name=lang.title(),
            extensions=sorted(exts),
            dimensions=dims,
        ))
    return result


def discover_plugins(*, cache: _PluginCache | None = None) -> list[PluginInfo]:
    """Return available plugin metadata from detection.json + dimensions.json.

    Results are cached for _PLUGIN_CACHE_TTL seconds so that configuration
    changes are picked up on the next request after the TTL expires.

    Pass *cache* to override the module-level cache (useful for testing).
    """
    _cache = cache if cache is not None else _plugin_cache
    cached = _cache.get()
    if cached is not None:
        return cached

    paths = default_paths()
    if paths.detection_file.exists() and paths.dimensions_file.exists():
        result = _discover_from_detection(paths.detection_file, paths.dimensions_file)
        _cache.set(result)
        return result

    return []
