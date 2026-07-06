"""Metadata and detection helpers for the filesystem action provider."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from quodeq.services.ports import RunInfo, read_run_data, safe_read_dir, summarize_dimensions

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from quodeq.core.scoring.params import ScoringParams


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
    params: "ScoringParams | None" = None,
) -> tuple[str | None, float | None, int | None]:
    """Compute accumulated grade and score across all runs. Returns (grade, score, files).

    The card summary applies the same project-wide dismiss/delete rescore as
    every other read path (see the ``_rescore_dimension`` step below), so the
    repositories-screen grade agrees with the Overview / explorer / trend.
    *params* (loaded from the saved formula when None) keeps the aggregate
    threshold labels and dimension weights consistent with the dashboard.
    """
    if params is None:
        from quodeq.services import grade_formula  # noqa: PLC0415
        params = grade_formula.load_params()

    from quodeq.services.score_cache import (  # noqa: PLC0415
        accumulated_cache_version, cached_project_summary, per_run_versions,
    )
    project_dir = reports_root / entry_name
    run_versions = per_run_versions(project_dir, entry_name, params, [r.run_id for r in runs])
    version = accumulated_cache_version(project_dir, params, run_versions, as_of=None)

    def _compute() -> dict:
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
            # Apply the project-wide dismiss/delete rescore so the card agrees
            # with every other read path (detail/explorer/dashboard/trend all
            # route through ``scored_run_dimensions``, i.e. read_run_data +
            # ``_rescore_dimension``). ``read_run_data`` returns the raw scan;
            # its SQL grade overlay reflects dismisses only when the run is
            # freshly projected, and NEVER reflects deletions. Without this the
            # project-card grade kept a stale, too-low value for any project
            # with deletions (or dismissals on a not-yet-reprojected run) —
            # diverging from the score shown everywhere else.
            from quodeq.services.deleted import deleted_keys  # noqa: PLC0415
            from quodeq.services.dismissed import dismissed_keys  # noqa: PLC0415
            from quodeq.services.rescore import _rescore_dimension  # noqa: PLC0415
            dismissed = dismissed_keys(project_dir)
            deleted = deleted_keys(project_dir)
            if dismissed or deleted:
                acc_dims = [
                    _rescore_dimension(d, dismissed, deleted, params=params)
                    for d in acc_dims
                ]
            # Scope the card summary to the project's current dimension standard
            # — the union of dimensions configured by the last few ELIGIBLE runs
            # — dropping stale dims (e.g. clean-architecture) that linger via old
            # runs / evaluation.db drift. ``runs`` here are NOT eligibility-
            # filtered (runs[0] may be in_progress), so the helper's internal
            # eligible filter keeps this symmetric with the accumulated path.
            # Fail-open: an empty standard set keeps every dim.
            from quodeq.services._run_dimensions import current_standard_dimensions  # noqa: PLC0415
            from quodeq.services.accumulated import _scope_to_configured  # noqa: PLC0415
            standard = current_standard_dimensions(reports_root, entry_name, runs)
            acc_dims = _scope_to_configured(acc_dims, standard)
            if not acc_dims:
                return {"grade": None, "score": None, "files": files_count}
            summary = summarize_dimensions(acc_dims, params)
            return {"grade": summary.overall_grade, "score": summary.numeric_average, "files": files_count}
        except (OSError, json.JSONDecodeError, KeyError):
            return {"grade": None, "score": None, "files": None}

    payload = cached_project_summary(entry_name, version, _compute)
    return payload["grade"], payload["score"], payload["files"]


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
    except OSError as e:
        _logger.warning("Could not read fingerprint dir %s: %s", project_dir, e)
    return False
