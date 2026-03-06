from __future__ import annotations

import json
from pathlib import Path

RUNTIME_PRESETS: dict[str, dict] = {
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

    # plugin.json
    (plugin_dir / "plugin.json").write_text(json.dumps({
        "id": runtime,
        "name": preset["display_name"],
        "version": "1.0.0",
        "engine_version": ">=2.0.0",
        "detects": {
            "extensions": preset["extensions"],
            "config_files": preset["config_files"],
        },
    }, indent=2) + "\n")

    # dimensions.json
    (plugin_dir / "dimensions.json").write_text(json.dumps({
        "applies": [
            {"id": "maintainability", "weight": 1.0, "iso_25010": "Maintainability", "source": "ISO/IEC 25010:2023"},
            {"id": "reliability", "weight": 1.0, "iso_25010": "Reliability", "source": "ISO/IEC 25010:2023"},
            {"id": "security", "weight": 1.2, "iso_25010": "Security", "source": "OWASP ASVS L1"},
            {"id": "performance", "weight": 0.8, "iso_25010": "Performance Efficiency", "source": "ISO/IEC 25010:2023"},
        ],
        "excludes": ["usability", "flexibility"],
    }, indent=2) + "\n")

    # knowledge directory
    knowledge_dir = plugin_dir / "knowledge"
    knowledge_dir.mkdir()

    (knowledge_dir / "practices.json").write_text(json.dumps({
        "runtime": runtime,
        "version": "1.0.0",
        "source": "manually curated",
        "practices": [],
    }, indent=2) + "\n")

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

    return plugin_dir
