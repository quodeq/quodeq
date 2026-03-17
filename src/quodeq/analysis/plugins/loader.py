"""Plugin loader — discovers and validates evaluator plugin directories."""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Iterator

_logger = logging.getLogger(__name__)

from quodeq.analysis.plugins.schema_validator import (
    validate_plugin,
    validate_dimensions,
)
from quodeq.shared.utils import read_json


def _check_engine_version(plugin_data: dict, plugin_dir: Path) -> None:
    """Warn if the plugin's engine_version constraint is not satisfied.

    Uses ``packaging.specifiers`` when available; silently skips the check if
    the library is absent or the constraint cannot be parsed.
    """
    constraint = plugin_data.get("engine_version")
    if not constraint:
        return
    try:
        from importlib.metadata import version as _pkg_version
        from packaging.specifiers import SpecifierSet
        from packaging.version import Version
        engine_ver = Version(_pkg_version("quodeq"))
        if engine_ver not in SpecifierSet(constraint, prereleases=True):
            import warnings
            warnings.warn(
                f"Plugin '{plugin_data.get('id', plugin_dir.name)}' requires "
                f"quodeq {constraint} but {engine_ver} is installed. "
                "The plugin may not work correctly.",
                UserWarning,
                stacklevel=3,
            )
    except (ImportError, ValueError, TypeError) as exc:
        _logger.debug("Version check skipped for %s: %s", plugin_dir.name, exc)


def scan_plugin_dirs(evaluators_dir: Path) -> Iterator[Path]:
    """Yield valid plugin directories (non-underscore dirs with plugin.json)."""
    if not evaluators_dir.exists():
        return
    for path in sorted(evaluators_dir.iterdir()):
        if path.is_dir() and not path.name.startswith("_") and (path / "plugin.json").exists():
            yield path


def discover_plugins(evaluators_dir: Path) -> list[dict]:
    """Discover all valid plugins in evaluators_dir."""
    plugins = []
    for path in scan_plugin_dirs(evaluators_dir):
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
    _check_engine_version(plugin_data, plugin_dir)

    dims_data = read_json(plugin_dir / "dimensions.json")
    errors = validate_dimensions(dims_data)
    if errors:
        raise ValueError(f"dimensions.json: {'; '.join(errors)}")

    return {
        "plugin": plugin_data,
        "dimensions": dims_data,
    }


def load_universal_dimensions(dimensions_file: Path) -> dict:
    """Load and validate the universal dimensions.json config.

    Returns the parsed dimensions dict.
    Raises ValueError on validation failure.
    """
    dims_data = read_json(dimensions_file)
    errors = validate_dimensions(dims_data)
    if errors:
        raise ValueError(f"dimensions.json: {'; '.join(errors)}")
    return dims_data


def _try_load(plugin_dir: Path) -> dict[str, object] | None:
    """Try loading a plugin from *plugin_dir*, returning None on failure."""
    plugin_file = plugin_dir / "plugin.json"
    if not plugin_file.exists():
        return None
    try:
        data = read_json(plugin_file)
        errors = validate_plugin(data)
        if errors:
            _logger.warning("Plugin %s has validation errors: %s", plugin_dir.name, "; ".join(errors))
            return None
        data["_path"] = str(plugin_dir)
        return data
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        _logger.warning("Failed to load plugin %s: %s", plugin_dir.name, exc)
        return None
