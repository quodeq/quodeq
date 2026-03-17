"""Scan evaluator directories and return plugin metadata."""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from quodeq.core.types import PluginDimension, PluginInfo
from quodeq.engine.plugin_loader import scan_plugin_dirs
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
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        pass

    result: list[PluginInfo] = []
    for lang, exts in sorted(lang_extensions.items()):
        result.append(PluginInfo(
            id=lang,
            name=lang.title(),
            extensions=sorted(exts),
            dimensions=dims,
        ))
    return result


def discover_plugins(evaluators_dir: Path | None = None, *, cache: _PluginCache | None = None) -> list[PluginInfo]:
    """Scan the evaluators directory and return plugin metadata.

    Results are cached for _PLUGIN_CACHE_TTL seconds so that plugins installed
    at runtime (without a process restart) are picked up on the next request
    after the TTL expires.

    Pass *cache* to override the module-level cache (useful for testing).
    """
    _cache = cache if cache is not None else _plugin_cache
    if evaluators_dir is None:
        cached = _cache.get()
        if cached is not None:
            return cached

    # Try universal mode first
    paths = default_paths()
    if evaluators_dir is None and paths.detection_file.exists() and paths.dimensions_file.exists():
        result = _discover_from_detection(paths.detection_file, paths.dimensions_file)
        _cache.set(result)
        return result

    # Legacy mode: scan evaluator directories
    evaluators_root = evaluators_dir or paths.evaluators_dir
    result: list[PluginInfo] = []
    for child in scan_plugin_dirs(evaluators_root):
        try:
            plugin_data = read_json(child / "plugin.json")
            dims_file = child / "dimensions.json"
            dims_data = read_json(dims_file) if dims_file.exists() else {"applies": []}
            result.append(PluginInfo(
                id=plugin_data.get("id", child.name),
                name=plugin_data.get("name", child.name),
                extensions=plugin_data.get("detects", {}).get("extensions", []),
                dimensions=[
                    PluginDimension(id=d["id"], weight=d.get("weight", 1), iso_25010=d.get("iso_25010"))
                    for d in dims_data.get("applies", [])
                ],
            ))
        except (KeyError, ValueError, OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            _logger.warning("Skipping plugin %s: %s", child.name, exc)
            continue
    _cache.set(result)
    return result
