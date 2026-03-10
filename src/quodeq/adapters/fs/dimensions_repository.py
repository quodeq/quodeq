"""Filesystem-backed repository for quality dimension definitions."""

from __future__ import annotations

import json
from pathlib import Path

from quodeq.ports.data_errors import NotFoundError


class FilesystemDimensionsRepository:
    """Read dimension data from JSON files on the local filesystem."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def list_dimensions(self) -> list[str]:
        """Return sorted names of all available dimensions."""
        dimensions_dir = self._root / "dimensions"
        if not dimensions_dir.exists():
            raise NotFoundError(f"Dimensions directory not found: {dimensions_dir}")
        return sorted(path.stem for path in dimensions_dir.glob("*.json") if path.is_file())

    def get_dimension(self, name: str) -> dict:
        """Load and return a single dimension definition by name."""
        path = self._root / "dimensions" / f"{name}.json"
        if not path.exists():
            raise NotFoundError(f"Dimension not found: {path}")
        return json.loads(path.read_text())
