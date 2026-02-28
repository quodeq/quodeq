import json
from pathlib import Path

from codecompass.ports.data_errors import NotFoundError


class FilesystemEvaluatorsRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    def list_evaluators(self, discipline: str) -> list[str]:
        evaluators_dir = self._root / "evaluators" / discipline
        if not evaluators_dir.exists():
            raise NotFoundError(f"Evaluators directory not found: {evaluators_dir}")
        return sorted(path.stem for path in evaluators_dir.glob("*.json") if path.is_file())

    def get_evaluator(self, discipline: str, dimension: str) -> dict:
        path = self._root / "evaluators" / discipline / f"{dimension}.json"
        if not path.exists():
            raise NotFoundError(f"Evaluator not found: {path}")
        return json.loads(path.read_text())
