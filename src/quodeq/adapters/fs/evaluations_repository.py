"""Filesystem-backed repository for evaluation reports."""

import json
from pathlib import Path

from quodeq.ports.data_errors import NotFoundError


class FilesystemEvaluationsRepository:
    """Read evaluation report data from JSON files on the local filesystem."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def list_reports(self) -> list[str]:
        """Return sorted IDs of all available evaluation reports."""
        evaluations_dir = self._root / "evaluations"
        if not evaluations_dir.exists():
            raise NotFoundError(f"Evaluations directory not found: {evaluations_dir}")
        return sorted(path.stem for path in evaluations_dir.glob("*.json") if path.is_file())

    def get_report(self, report_id: str) -> dict:
        """Load and return a single evaluation report by ID."""
        path = self._root / "evaluations" / f"{report_id}.json"
        if not path.exists():
            raise NotFoundError(f"Report not found: {path}")
        return json.loads(path.read_text())
