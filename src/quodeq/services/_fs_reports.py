"""Report and dashboard reading helpers for the filesystem action provider."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.config.paths import default_paths
from quodeq.core.types import ViolationResponse, ViolationSummary, to_camel_dict
from quodeq.services.accumulated import compute_accumulated
from quodeq.services.dashboard import build_dashboard
from quodeq.services.violations import aggregate_violations, resolve_dimension_eval


def get_dashboard(reports_dir: str, project: str, run: str) -> dict[str, Any]:
    """Return the dashboard payload for a specific project run."""
    return build_dashboard(reports_dir, project, run)


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
    from quodeq.services.violations import _ResolveOptions
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
