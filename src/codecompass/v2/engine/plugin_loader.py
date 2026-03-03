from __future__ import annotations
import json
from pathlib import Path


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
    plugin_file = plugin_dir / "plugin.json"
    return json.loads(plugin_file.read_text())


def _try_load(plugin_dir: Path) -> dict | None:
    plugin_file = plugin_dir / "plugin.json"
    if not plugin_file.exists():
        return None
    try:
        data = json.loads(plugin_file.read_text())
        data["_path"] = str(plugin_dir)
        return data
    except (json.JSONDecodeError, KeyError):
        return None
