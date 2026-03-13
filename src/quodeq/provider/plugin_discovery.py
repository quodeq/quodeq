"""Scan evaluator directories and return plugin metadata."""
from __future__ import annotations

import json
import threading
import time
from typing import Any

from quodeq.engine.plugin_loader import scan_plugin_dirs

_PLUGIN_CACHE_TTL = 60  # seconds; allows runtime plugin changes to propagate
_plugin_cache: list[dict[str, Any]] | None = None
_plugin_cache_ts: float = 0.0
_plugin_cache_lock = threading.Lock()


def discover_plugins() -> list[dict[str, Any]]:
    """Scan the evaluators directory and return plugin metadata.

    Results are cached for _PLUGIN_CACHE_TTL seconds so that plugins installed
    at runtime (without a process restart) are picked up on the next request
    after the TTL expires.
    """
    global _plugin_cache, _plugin_cache_ts
    now = time.monotonic()
    with _plugin_cache_lock:
        if _plugin_cache is not None and now - _plugin_cache_ts < _PLUGIN_CACHE_TTL:
            return _plugin_cache
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
    with _plugin_cache_lock:
        _plugin_cache = result
        _plugin_cache_ts = now
    return result
