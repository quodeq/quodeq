"""Filesystem path resolution for quodeq configuration directories."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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
    for line in paths.env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in target:
            target[key] = os.path.expanduser(value)


def _looks_like_project_root(root: Path) -> bool:
    return (
        (root / "prompts").is_dir()
        and (root / "evaluators").is_dir()
    )


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
    _FALLBACK_PARENT_DEPTH = 3
    if len(module_path.parents) > _FALLBACK_PARENT_DEPTH:
        root = module_path.parents[_FALLBACK_PARENT_DEPTH]
    else:
        root = module_path.parent
    return ConfigPaths.from_root(root)
