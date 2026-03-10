"""Filesystem path resolution for quodeq configuration directories."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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

    @classmethod
    def from_root(cls, root: Path, version: str | None = None) -> "ConfigPaths":
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


def _looks_like_project_root(root: Path) -> bool:
    return (
        (root / "prompts").is_dir()
        and (root / "evaluators").is_dir()
    )


def default_paths(version: str | None = None) -> ConfigPaths:
    """Locate the project root automatically and return its ConfigPaths."""
    module_path = Path(__file__).resolve()
    for root in module_path.parent.parents:
        if _looks_like_project_root(root):
            return ConfigPaths.from_root(root, version=version)

    root = module_path.parents[3]
    return ConfigPaths.from_root(root, version=version)
