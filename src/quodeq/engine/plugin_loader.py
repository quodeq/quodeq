"""Plugin loader — discovers and validates evaluator plugin directories."""
from __future__ import annotations
import json
from pathlib import Path

from quodeq.engine.schema_validator import (
    validate_plugin,
    validate_dimensions,
)
from quodeq.utils import read_json


def discover_plugins(evaluators_dir: Path) -> list[dict]:
    """Discover all valid plugins in evaluators_dir.
    Ignores directories starting with '_'.
    """
    plugins = []
    if not evaluators_dir.exists():
        return plugins
    for path in sorted(evaluators_dir.iterdir()):
        if path.is_dir() and not path.name.startswith("_"):
            plugin = _try_load(path)
            if plugin:
                plugins.append(plugin)
    return plugins


def load_plugin(plugin_dir: Path) -> dict:
    """Load and return the plugin.json contents from a plugin directory."""
    return read_json(plugin_dir / "plugin.json")


def load_plugin_full(plugin_dir: Path) -> dict:
    """Load and validate all plugin JSON files into one dict.

    Returns {"plugin": dict, "dimensions": dict}.
    Raises ValueError on validation failure.
    """
    plugin_data = read_json(plugin_dir / "plugin.json")
    errors = validate_plugin(plugin_data)
    if errors:
        raise ValueError(f"plugin.json: {'; '.join(errors)}")

    dims_data = read_json(plugin_dir / "dimensions.json")
    errors = validate_dimensions(dims_data)
    if errors:
        raise ValueError(f"dimensions.json: {'; '.join(errors)}")

    return {
        "plugin": plugin_data,
        "dimensions": dims_data,
    }


def _try_load(plugin_dir: Path) -> dict | None:
    plugin_file = plugin_dir / "plugin.json"
    if not plugin_file.exists():
        return None
    try:
        data = read_json(plugin_file)
        errors = validate_plugin(data)
        if errors:
            return None
        data["_path"] = str(plugin_dir)
        return data
    except (json.JSONDecodeError, KeyError):
        return None
