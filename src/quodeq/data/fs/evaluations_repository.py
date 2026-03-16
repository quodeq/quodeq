"""Filesystem-backed repository for evaluation reports."""

from __future__ import annotations

from pathlib import Path

from quodeq.data.fs._json_loader import get_json_file, list_json_dir
from quodeq.shared.validation import validate_path_segment


class FilesystemEvaluationsRepository:
    """Read evaluation report data from JSON files on the local filesystem.

    Uses ``list_json_dir`` and ``get_json_file`` helpers shared with
    ``FilesystemDimensionsRepository`` to avoid duplicating the list/get pattern.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def list_reports(self) -> list[str]:
        """Return sorted IDs of all available evaluation reports.

        Example::

            repo = FilesystemEvaluationsRepository(Path("/data"))
            ids = repo.list_reports()  # ["report-001", "report-002"]
        """
        return list_json_dir(self._root / "evaluations", "Evaluations directory not found")

    def get_report(self, report_id: str) -> dict:
        """Load and return a single evaluation report by ID.

        Example::

            report = repo.get_report("report-001")
        """
        validate_path_segment(report_id)
        return get_json_file(self._root / "evaluations", report_id, "Report not found")
