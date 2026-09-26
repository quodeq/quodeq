"""Report and dashboard reading helpers for the filesystem action provider."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.config.paths import default_paths
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.types import EvalPending, ViolationResponse, ViolationSummary
from quodeq.services.accumulated import compute_accumulated
from quodeq.services.dashboard import build_dashboard
from quodeq.services.violations import ResolveOptions, aggregate_violations, resolve_dimension_eval
from quodeq.services.wiring import read_scan_json, scan_json_exists

_SCAN_FILENAME = "scan.json"


def _enrich_with_coverage(
    reports_dir: str, project: str, payload: dict[str, Any], *, log: LogSink = NULL_LOG,
) -> dict[str, Any]:
    """Add coverage fields from scan.json if available."""
    project_dir = Path(reports_dir) / project
    if not scan_json_exists(project_dir):
        return payload
    scan = read_scan_json(project_dir)
    if scan is None:
        log.debug(f"coverage enrichment skipped for {project}: invalid scan.json")
        return payload
    total = scan.get("total_files", 0)
    payload["totalFiles"] = total
    # Compute analyzed_files from the files_count already tracked in run data.
    # The existing read_accumulated_summary returns files_count from manifests.
    # Use it as the analyzed count (it counts unique source files seen across runs).
    files_count = payload.get("filesCount") or payload.get("files_count")
    if files_count and total:
        payload["analyzedFiles"] = min(files_count, total)
    else:
        payload["analyzedFiles"] = None
    return payload


def get_dashboard(reports_dir: str, project: str, run: str, *, log: LogSink = NULL_LOG) -> dict[str, Any]:
    """Return the dashboard payload for a specific project run."""
    payload = build_dashboard(reports_dir, project, run)
    return _enrich_with_coverage(reports_dir, project, payload, log=log)


def get_accumulated(
    reports_dir: str, project: str, as_of: str | None, *, log: LogSink = NULL_LOG,
) -> dict[str, Any] | None:
    """Return accumulated dimension data across all runs up to as_of."""
    return compute_accumulated(reports_dir, project, as_of, log=log)


def get_dimension_eval(
    reports_dir: str,
    project: str,
    run_id: str,
    dimension: str,
    *,
    compiled_dir: Path | None = None,
    evaluators_dir: Path | None = None,
) -> ViolationResponse | dict[str, Any] | EvalPending | None:
    """Return parsed evaluation data for a single dimension in a run.

    The wire shaping (camelCase, the waiting/202 body) is owned by the
    routes: this returns whatever ``resolve_dimension_eval`` produced (a
    ``ViolationResponse``, or a stored camelCase dict), ``EvalPending`` when
    the run directory exists but nothing has been written yet, or ``None``
    when the run itself doesn't exist.
    """
    base = (Path(reports_dir) / project / run_id).resolve()
    if not base.is_relative_to(Path(reports_dir).resolve()):
        return None
    effective_compiled = compiled_dir or default_paths().standards_dir / "compiled"
    effective_evaluators = evaluators_dir if evaluators_dir is not None else default_paths().evaluators_dir
    result = resolve_dimension_eval(
        base, project, run_id, dimension,
        options=ResolveOptions(
            compiled_dir=effective_compiled if effective_compiled.exists() else None,
            evaluators_dir=effective_evaluators if effective_evaluators.exists() else None,
        ),
    )
    if result is not None:
        return result
    if base.is_dir():
        return EvalPending(project, run_id, dimension)
    return None


def get_violations(reports_dir: str, project: str, run_id: str, *, log: LogSink = NULL_LOG) -> ViolationSummary:
    """Return aggregated violation counts and top files for a run."""
    dashboard = get_dashboard(reports_dir, project, run_id, log=log)
    return aggregate_violations(dashboard)
