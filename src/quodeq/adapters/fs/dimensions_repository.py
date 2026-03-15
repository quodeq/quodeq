"""Filesystem-backed repository for quality dimension definitions."""

from __future__ import annotations

from pathlib import Path

from quodeq.adapters.fs._json_loader import get_json_file, list_json_dir
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
        return list_json_dir(self._root / "dimensions", "Dimensions directory not found")

    def get_dimension(self, name: str) -> dict:
        """Load and return a single dimension definition by name.

        Example::

            repo = FilesystemDimensionsRepository(root)
            dim = repo.get_dimension('security')  # {'name': 'security', ...}
        """
        validate_path_segment(name)
        return get_json_file(self._root / "dimensions", name, "Dimension not found")
