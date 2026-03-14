"""Filesystem-backed repository for quality dimension definitions."""

from __future__ import annotations

from pathlib import Path

from quodeq.adapters.fs._json_loader import load_json_file
from quodeq.ports.data_errors import NotFoundError
from quodeq.shared.validation import validate_path_segment


class FilesystemDimensionsRepository:
    """Read dimension data from JSON files on the local filesystem."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def list_dimensions(self) -> list[str]:
        """Return sorted names of all available dimensions.

        Example::

            repo = FilesystemDimensionsRepository(root)
            names = repo.list_dimensions()  # ['maintainability', 'security', ...]
        """
        dimensions_dir = self._root / "dimensions"
        if not dimensions_dir.exists():
            raise NotFoundError(f"Dimensions directory not found: {dimensions_dir}")
        return sorted(path.stem for path in dimensions_dir.glob("*.json") if path.is_file())

    def get_dimension(self, name: str) -> dict:
        """Load and return a single dimension definition by name.

        Example::

            repo = FilesystemDimensionsRepository(root)
            dim = repo.get_dimension('security')  # {'name': 'security', ...}
        """
        validate_path_segment(name)
        path = self._root / "dimensions" / f"{name}.json"
        return load_json_file(path, f"Dimension not found: {name}")
