"""Filesystem path resolution for quodeq configuration directories.

Re-exports from internal modules to preserve the public API.
"""

from __future__ import annotations

from pathlib import Path

from quodeq.config._config_paths import ConfigPaths  # noqa: F401
from quodeq.config._env_loader import load_env_file  # noqa: F401

__all__ = ["ConfigPaths", "load_env_file", "default_paths"]

# Number of parent directory levels from this module to the project root
# (config -> quodeq -> src).
_FALLBACK_PARENT_DEPTH = 3

# Bundled data directory shipped inside the package.
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _looks_like_project_root(root: Path) -> bool:
    """Return True if *root* contains the expected quodeq data layout."""
    has_prompts = (root / "prompts").is_dir()
    has_detection = (root / "config" / "detection.json").is_file()
    return has_prompts and has_detection


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

    # Walk up from src/quodeq/config/paths.py to project root
    if len(module_path.parents) > _FALLBACK_PARENT_DEPTH:
        root = module_path.parents[_FALLBACK_PARENT_DEPTH]
    else:
        root = module_path.parent
    return ConfigPaths.from_root(root)
