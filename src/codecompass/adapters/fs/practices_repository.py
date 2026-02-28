import json
from pathlib import Path

from codecompass.ports.data_errors import NotFoundError


class FilesystemPracticesRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    def list_topics(self, discipline: str) -> list[str]:
        practices_dir = self._root / "practices" / discipline
        if not practices_dir.exists():
            raise NotFoundError(f"Practices directory not found: {practices_dir}")
        return sorted(path.stem for path in practices_dir.glob("*.json") if path.is_file())

    def get_practice(self, discipline: str, topic: str) -> dict:
        path = self._root / "practices" / discipline / f"{topic}.json"
        if not path.exists():
            raise NotFoundError(f"Practice not found: {path}")
        return json.loads(path.read_text())
