"""Filesystem path resolution for quodeq configuration directories."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

_logger = logging.getLogger(__name__)

# Number of parent directory levels from this module to the project root
# (config -> quodeq -> src).
_FALLBACK_PARENT_DEPTH = 3

# Bundled data directory shipped inside the package.
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class ConfigPaths:
    """Immutable set of resolved paths to all configuration directories and files."""

    root: Path
    evaluators_dir: Path
    practices_dir: Path
    dimensions_dir: Path
    prompts_dir: Path
    standards_dir: Path
    env_file: Path
    gitignore_file: Path

    @property
    def vroot(self) -> Path:
        """Return the versioned root path (currently identical to root)."""
        return self.root

    @property
    def disciplines_conf(self) -> Path:
        """Return the path to the disciplines configuration file."""
        return self.root / "config" / "disciplines.conf"

    @property
    def detection_file(self) -> Path:
        """Return the path to the universal detection.json config."""
        return self.root / "config" / "detection.json"

    @property
    def dimensions_file(self) -> Path:
        """Return the path to the universal dimensions.json config."""
        return self.root / "config" / "dimensions.json"

    @classmethod
    def from_root(cls, root: Path) -> "ConfigPaths":
        """Construct a ConfigPaths instance by deriving all paths from a root directory."""
        return cls(
            root=root,
            evaluators_dir=root / "evaluators",
            practices_dir=root / "practices",
            dimensions_dir=root / "dimensions",
            prompts_dir=root / "prompts",
            standards_dir=root / "standards",
            env_file=root / ".quodeq.env",
            gitignore_file=root / ".gitignore",
        )

    @classmethod
    def from_data_dir(cls, data_dir: Path) -> "ConfigPaths":
        """Construct a ConfigPaths from the bundled package data directory."""
        return cls.from_root(data_dir)


def load_env_file(paths: ConfigPaths, target: dict[str, str] | None = None) -> None:
    """Source all ``export VAR=value`` lines from ``.quodeq.env`` into *target*.

    *target* defaults to ``os.environ``.  Already-set keys are NOT
    overwritten, so explicit env takes precedence over the file.

    Pass an explicit *target* dict in tests to avoid mutating the real
    environment.
    """
    if target is None:
        target = os.environ
    if not paths.env_file.exists():
        return
    try:
        lines = paths.env_file.read_text().splitlines()
    except OSError as exc:
        _logger.warning("Failed to read env file %s: %s", paths.env_file, exc)
        return
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export "):]
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in target:
            target[key] = os.path.expanduser(value)


def _looks_like_project_root(root: Path) -> bool:
    # Accept both legacy layout (evaluators/) and new layout (config/detection.json)
    has_prompts = (root / "prompts").is_dir()
    has_evaluators = (root / "evaluators").is_dir()
    has_detection = (root / "config" / "detection.json").is_file()
    return has_prompts and (has_evaluators or has_detection)


def default_paths() -> ConfigPaths:
    """Return ConfigPaths from the bundled data directory, or the project root in dev."""
    # Prefer bundled data directory (works when installed as a package)
    if _DATA_DIR.is_dir() and _looks_like_project_root(_DATA_DIR):
        return ConfigPaths.from_data_dir(_DATA_DIR)

    # Fallback: walk up to the project root (development mode)
    module_path = Path(__file__).resolve()
    for root in module_path.parent.parents:
        if _looks_like_project_root(root):
            return ConfigPaths.from_root(root)

    # Walk up from src/quodeq/config/paths.py to project root (3 levels: config -> quodeq -> src)
    if len(module_path.parents) > _FALLBACK_PARENT_DEPTH:
        root = module_path.parents[_FALLBACK_PARENT_DEPTH]
    else:
        root = module_path.parent
    return ConfigPaths.from_root(root)
