"""Metadata and detection helpers for the filesystem action provider."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quodeq.services.ports import RunInfo, read_run_data, safe_read_dir, summarize_dimensions


def _read_scan_summary(reports_root: Path, entry_name: str) -> dict[str, Any]:
    """Read scan.json and return coverage fields, or empty dict if not available."""
    scan_path = reports_root / entry_name / "scan.json"
    if not scan_path.exists():
        return {}
    try:
        data = json.loads(scan_path.read_text(encoding="utf-8"))
        return {
            "scanDate": data.get("scanned_at"),
            "totalFiles": data.get("total_files"),
        }
    except (json.JSONDecodeError, OSError):
        return {}


def _check_path_exists(path: str | None, location: str | None) -> bool | None:
    """Return whether a local path exists, or None if not applicable."""
    if location == "local" and path:
        return Path(path).exists()
    return None


def _extract_project_metadata(info: dict[str, Any], entry_name: str) -> dict[str, Any]:
    """Extract and normalize optional metadata fields from repository info."""
    return {
        "name": info.get("name") or entry_name,
        "parent": info.get("parent") or None,
        "displayName": info.get("displayName") or None,
        "discipline": info.get("discipline") or None,
        "path": info.get("path") or None,
        "location": info.get("location") or None,
        "scopePath": info.get("scopePath") or None,
    }


def _read_repo_info(reports_root: Path, entry_name: str) -> dict[str, Any]:
    """Read repository_info.json for a project, returning an empty dict on failure."""
    info_path = reports_root / entry_name / "repository_info.json"
    if not info_path.exists():
        return {}
    try:
        return json.loads(info_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _read_accumulated_summary(
    reports_root: Path, entry_name: str, runs: list[RunInfo],
) -> tuple[str | None, float | None, int | None]:
    """Compute accumulated grade and score across all runs. Returns (grade, score, files)."""
    try:
        latest_by_dim: dict[str, object] = {}
        files_count: int | None = None
        for run in runs:
            dims = read_run_data(reports_root, entry_name, run.run_id)
            for d in dims:
                if d.dimension and d.dimension not in latest_by_dim:
                    latest_by_dim[d.dimension] = d
                if files_count is None and d.source_file_count:
                    files_count = d.source_file_count
        acc_dims = list(latest_by_dim.values())
        if not acc_dims:
            return None, None, files_count
        summary = summarize_dimensions(acc_dims)
        return summary.overall_grade, summary.numeric_average, files_count
    except (OSError, json.JSONDecodeError, KeyError):
        return None, None, None


def _read_language_stats(reports_root: Path, entry_name: str, runs: list[RunInfo]) -> dict[str, int]:
    """Read language_stats from the latest run's manifest.json."""
    for run in runs:
        manifest_path = reports_root / entry_name / run.run_id / "evidence" / "manifest.json"
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            stats = data.get("language_stats") or {}
            if stats:
                return {k.lstrip("."): v for k, v in stats.items()}
        except (json.JSONDecodeError, OSError):
            continue
    return {}


def _read_discipline_from_eval(eval_path: Path) -> str | None:
    """Try to read a discipline string from a single evidence JSON file."""
    try:
        return json.loads(eval_path.read_text(encoding="utf-8")).get("discipline") or None
    except (OSError, json.JSONDecodeError):
        return None


def _find_discipline_in_run(evidence_dir: Path) -> str | None:
    """Search a single run's evidence directory for a discipline string."""
    for ev in safe_read_dir(evidence_dir):
        if ev.name.endswith("_evidence.json"):
            found = _read_discipline_from_eval(Path(ev.path))
            if found:
                return found
    return None


def _infer_discipline(reports_root: Path, project: str) -> str | None:
    """Infer discipline from the most recent evidence file."""
    for run in sorted(safe_read_dir(reports_root / project), key=lambda e: e.name, reverse=True):
        if not run.is_dir():
            continue
        found = _find_discipline_in_run(reports_root / project / run.name / "evidence")
        if found:
            return found
    return None


def _has_fingerprints(reports_root: Path, project: str) -> bool:
    """Check if any evaluation run has fingerprint files for this project."""
    project_dir = reports_root / project
    if not project_dir.exists():
        return False
    try:
        for run_dir in sorted(project_dir.iterdir(), reverse=True):
            evidence_dir = run_dir / "evidence"
            if not evidence_dir.is_dir():
                continue
            if any(f.name.endswith("_fingerprint.json") for f in evidence_dir.iterdir()):
                return True
    except OSError:
        pass
    return False
