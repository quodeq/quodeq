"""Filesystem-backed repository for evaluator configuration files."""

from __future__ import annotations

from pathlib import Path

from quodeq.adapters.fs._json_loader import load_json_file
from quodeq.ports.data_errors import NotFoundError
from quodeq.shared.validation import validate_path_segment


class FilesystemEvaluatorsRepository:
    """Read evaluator definitions from JSON files on the local filesystem."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def list_evaluators(self, discipline: str) -> list[str]:
        """Return sorted names of all evaluators for a discipline."""
        validate_path_segment(discipline)
        evaluators_dir = self._root / "evaluators" / discipline
        if not evaluators_dir.exists():
            raise NotFoundError(f"Evaluators directory not found: {evaluators_dir}")
        return sorted(path.stem for path in evaluators_dir.glob("*.json") if path.is_file())

    def get_evaluator(self, discipline: str, dimension: str) -> dict:
        """Load and return a single evaluator definition by discipline and dimension."""
        validate_path_segment(discipline, dimension)
        path = self._root / "evaluators" / discipline / f"{dimension}.json"
        return load_json_file(path, f"Evaluator not found: {discipline}/{dimension}")
