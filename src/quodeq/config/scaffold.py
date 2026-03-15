"""Scaffold boilerplate plugin directories from runtime presets."""
from __future__ import annotations

import importlib.metadata
import json
import logging
import os
import shutil
from pathlib import Path

_DEFAULT_PLUGIN_VERSION = "1.0.0"


def _default_dimension_weight() -> float:
    """Return the default dimension weight (reads env at call time)."""
    return float(os.environ.get("QUODEQ_DEFAULT_DIM_WEIGHT", "1.0"))


def _security_dimension_weight() -> float:
    """Return the security dimension weight (reads env at call time)."""
    return float(os.environ.get("QUODEQ_SECURITY_DIM_WEIGHT", "1.2"))


def _performance_dimension_weight() -> float:
    """Return the performance dimension weight (reads env at call time)."""
    return float(os.environ.get("QUODEQ_PERFORMANCE_DIM_WEIGHT", "0.8"))

_logger = logging.getLogger(__name__)


def _min_engine_version() -> str:
    """Derive the engine_version constraint from the installed quodeq version."""
    from quodeq import __version__
    if __version__:
        return f"=={__version__}"
    try:
        from importlib.metadata import version as _pkg_version
        return f"=={_pkg_version('quodeq')}"
    except importlib.metadata.PackageNotFoundError:
        _logger.debug("Could not determine quodeq version for engine constraint")
        return ">=0.4.0"


def _load_runtime_presets() -> dict[str, dict]:
    """Load runtime presets from the bundled JSON file, falling back to hardcoded defaults."""
    _FALLBACK: dict[str, dict] = {
        "typescript": {
            "display_name": "TypeScript / Node.js",
            "extensions": [".ts", ".tsx"],
            "config_files": ["tsconfig.json", "package.json"],
        },
        "kotlin": {
            "display_name": "Kotlin / JVM",
            "extensions": [".kt", ".kts"],
            "config_files": ["build.gradle.kts", "build.gradle"],
        },
        "python": {
            "display_name": "Python",
            "extensions": [".py"],
            "config_files": ["pyproject.toml", "setup.py", "requirements.txt"],
        },
        "bash": {
            "display_name": "Bash / Shell",
            "extensions": [".sh", ".bash"],
            "config_files": [".bashrc", "Makefile"],
        },
        "java": {
            "display_name": "Java / JVM",
            "extensions": [".java"],
            "config_files": ["pom.xml", "build.gradle"],
        },
        "mobile_ios": {
            "display_name": "iOS / Swift",
            "extensions": [".swift"],
            "config_files": ["Package.swift", "Podfile"],
        },
    }
    json_path = Path(__file__).resolve().parent.parent / "data" / "config" / "runtime_presets.json"
    try:
        return json.loads(json_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _logger.debug("Failed to load runtime presets from %s, using fallback: %s", json_path, exc)
        return _FALLBACK


RUNTIME_PRESETS: dict[str, dict] = _load_runtime_presets()


def _write_plugin_json(plugin_dir: Path, runtime: str, preset: dict) -> None:
    """Write plugin.json with detection metadata."""
    (plugin_dir / "plugin.json").write_text(json.dumps({
        "id": runtime,
        "name": preset["display_name"],
        "version": _DEFAULT_PLUGIN_VERSION,
        "engine_version": _min_engine_version(),
        "detects": {
            "extensions": preset["extensions"],
            "config_files": preset["config_files"],
        },
    }, indent=2) + "\n")


def _write_dimensions_json(plugin_dir: Path) -> None:
    """Write dimensions.json with default dimension weights."""
    (plugin_dir / "dimensions.json").write_text(json.dumps({
        "applies": [
            {"id": "maintainability", "weight": _default_dimension_weight(), "iso_25010": "Maintainability", "source": "ISO/IEC 25010:2023"},
            {"id": "reliability", "weight": _default_dimension_weight(), "iso_25010": "Reliability", "source": "ISO/IEC 25010:2023"},
            {"id": "security", "weight": _security_dimension_weight(), "iso_25010": "Security", "source": "OWASP ASVS L1"},
            {"id": "performance", "weight": _performance_dimension_weight(), "iso_25010": "Performance Efficiency", "source": "ISO/IEC 25010:2023"},
        ],
        "excludes": ["usability", "flexibility"],
    }, indent=2) + "\n")


def scaffold_plugin(runtime: str, evaluators_dir: Path) -> Path:
    """Generate a full plugin directory with schema-valid boilerplate.

    Returns the path to the created plugin directory.
    Raises ValueError if runtime is unknown or directory already exists.
    """
    if runtime not in RUNTIME_PRESETS:
        raise ValueError(f"Unknown runtime: {runtime}. Available: {', '.join(sorted(RUNTIME_PRESETS))}")

    plugin_dir = evaluators_dir / runtime
    if plugin_dir.exists():
        raise ValueError(f"Plugin directory already exists: {plugin_dir}")

    preset = RUNTIME_PRESETS[runtime]
    plugin_dir.mkdir(parents=True)

    try:
        _write_plugin_json(plugin_dir, runtime, preset)
        _write_dimensions_json(plugin_dir)

        knowledge_dir = plugin_dir / "knowledge"
        knowledge_dir.mkdir()
        (knowledge_dir / "analysis.md").write_text(
            f"# {preset['display_name']} Codebase Analysis Guidance\n\n"
            f"## Where to look first\n\n"
            f"### Security hotspots\n"
            f"- Hardcoded secrets and credentials\n\n"
            f"### Maintainability signals\n"
            f"- File size and complexity\n\n"
            f"### Reliability signals\n"
            f"- Error handling patterns\n\n"
            f"### Performance signals\n"
            f"- Resource management\n"
        )
    except OSError:
        shutil.rmtree(plugin_dir, ignore_errors=True)
        raise

    return plugin_dir
