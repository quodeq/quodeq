import json
from pathlib import Path

from quodeq.ports.data_errors import NotFoundError


class FilesystemDimensionsRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    def list_dimensions(self) -> list[str]:
        dimensions_dir = self._root / "dimensions"
        if not dimensions_dir.exists():
            raise NotFoundError(f"Dimensions directory not found: {dimensions_dir}")
        return sorted(path.stem for path in dimensions_dir.glob("*.json") if path.is_file())

    def get_dimension(self, name: str) -> dict:
        path = self._root / "dimensions" / f"{name}.json"
        if not path.exists():
            raise NotFoundError(f"Dimension not found: {path}")
        return json.loads(path.read_text())
