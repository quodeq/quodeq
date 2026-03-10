"""Scan evaluator directories and return plugin metadata."""
from __future__ import annotations

import json
from typing import Any

from quodeq.engine.plugin_loader import scan_plugin_dirs


def discover_plugins() -> list[dict[str, Any]]:
    """Scan the evaluators directory and return plugin metadata."""
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
        except (KeyError, ValueError):
            continue
    return result
