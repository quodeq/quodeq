"""ConfigPaths dataclass: immutable set of resolved configuration paths."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConfigPaths:
    """Immutable set of resolved paths to all configuration directories and files."""

    root: Path
    prompts_dir: Path | None = None
    standards_dir: Path | None = None
    env_file: Path | None = None
    gitignore_file: Path | None = None

    @property
    def evaluators_dir(self) -> Path:
        """Global directory for custom evaluator JSON files."""
        return Path(os.environ.get("QUODEQ_EVALUATORS_DIR", str(Path.home() / ".quodeq" / "evaluators")))

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
            prompts_dir=root / "prompts",
            standards_dir=root / "standards",
            env_file=root / ".quodeq.env",
            gitignore_file=root / ".gitignore",
        )

    @classmethod
    def from_data_dir(cls, data_dir: Path) -> "ConfigPaths":
        """Construct a ConfigPaths from the bundled package data directory."""
        return cls.from_root(data_dir)
