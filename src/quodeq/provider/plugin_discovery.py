"""Scan evaluator directories and return plugin metadata."""
from __future__ import annotations

import json
import threading
import time
from typing import Any

from quodeq.engine.plugin_loader import scan_plugin_dirs

_PLUGIN_CACHE_TTL = 60  # seconds; allows runtime plugin changes to propagate


class _PluginCache:
    """Thread-safe TTL cache for plugin metadata."""

    def __init__(self, ttl: float = _PLUGIN_CACHE_TTL) -> None:
        self._lock = threading.Lock()
        self._cache: list[dict[str, Any]] | None = None
        self._ts: float = 0.0
        self._ttl = ttl

    def get(self) -> list[dict[str, Any]] | None:
        with self._lock:
            if self._cache is not None and time.monotonic() - self._ts < self._ttl:
                return self._cache
        return None

    def set(self, data: list[dict[str, Any]]) -> None:
        with self._lock:
            self._cache = data
            self._ts = time.monotonic()


_plugin_cache = _PluginCache()


def discover_plugins() -> list[dict[str, Any]]:
    """Scan the evaluators directory and return plugin metadata.

    Results are cached for _PLUGIN_CACHE_TTL seconds so that plugins installed
    at runtime (without a process restart) are picked up on the next request
    after the TTL expires.
    """
    cached = _plugin_cache.get()
    if cached is not None:
        return cached
    from quodeq.config.paths import default_paths
    evaluators_root = default_paths().evaluators_dir
    result: list[dict[str, Any]] = []
    for child in scan_plugin_dirs(evaluators_root):
        try:
            plugin_data = json.loads((child / "plugin.json").read_text())
            dims_file = child / "dimensions.json"
            dims_data = json.loads(dims_file.read_text()) if dims_file.exists() else {"applies": []}
            result.append({
                "id": plugin_data.get("id", child.name),
                "name": plugin_data.get("name", child.name),
                "extensions": plugin_data.get("detects", {}).get("extensions", []),
                "dimensions": [
                    {"id": d["id"], "weight": d.get("weight", 1), "iso_25010": d.get("iso_25010")}
                    for d in dims_data.get("applies", [])
                ],
            })
        except (KeyError, ValueError, OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
    _plugin_cache.set(result)
    return result
