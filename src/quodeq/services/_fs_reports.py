"""Report and dashboard reading helpers for the filesystem action provider."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quodeq.config.paths import default_paths
from quodeq.core.types import ViolationResponse, ViolationSummary, to_camel_dict
from quodeq.services.accumulated import compute_accumulated
from quodeq.services.dashboard import build_dashboard
from quodeq.services.violations import _ResolveOptions, aggregate_violations, resolve_dimension_eval

_SCAN_FILENAME = "scan.json"


def _enrich_with_coverage(reports_dir: str, project: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Add coverage fields from scan.json if available."""
    scan_path = Path(reports_dir) / project / _SCAN_FILENAME
    if not scan_path.exists():
        return payload
    try:
        scan = json.loads(scan_path.read_text(encoding="utf-8"))
        total = scan.get("total_files", 0)
        payload["totalFiles"] = total
        # Compute analyzed_files from the files_count already tracked in run data.
        # The existing _read_accumulated_summary returns files_count from manifests.
        # Use it as the analyzed count (it counts unique source files seen across runs).
        files_count = payload.get("filesCount") or payload.get("files_count")
        if files_count and total:
            payload["analyzedFiles"] = min(files_count, total)
        else:
            payload["analyzedFiles"] = None
    except (json.JSONDecodeError, OSError):
        pass
    return payload


def get_dashboard(reports_dir: str, project: str, run: str) -> dict[str, Any]:
    """Return the dashboard payload for a specific project run."""
    payload = build_dashboard(reports_dir, project, run)
    return _enrich_with_coverage(reports_dir, project, payload)


def get_accumulated(reports_dir: str, project: str, as_of: str | None) -> dict[str, Any] | None:
    """Return accumulated dimension data across all runs up to as_of."""
    return compute_accumulated(reports_dir, project, as_of)


def get_dimension_eval(
    reports_dir: str,
    project: str,
    run_id: str,
    dimension: str,
    *,
    compiled_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Return parsed evaluation data for a single dimension in a run."""
    base = (Path(reports_dir) / project / run_id).resolve()
    if not base.is_relative_to(Path(reports_dir).resolve()):
        return None
    effective_compiled = compiled_dir or default_paths().standards_dir / "compiled"
    result = resolve_dimension_eval(
        base, project, run_id, dimension,
        options=_ResolveOptions(compiled_dir=effective_compiled if effective_compiled.exists() else None),
    )
    if result is not None:
        return to_camel_dict(result) if isinstance(result, ViolationResponse) else result
    if base.is_dir():
        return {"waiting": True, "project": project, "runId": run_id, "dimension": dimension}
    return None


def get_violations(reports_dir: str, project: str, run_id: str) -> ViolationSummary:
    """Return aggregated violation counts and top files for a run."""
    dashboard = get_dashboard(reports_dir, project, run_id)
    return aggregate_violations(dashboard)
