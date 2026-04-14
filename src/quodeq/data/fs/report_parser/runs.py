"""Run discovery, date parsing, and report aggregation for filesystem reports.

The module-level functions (``read_run_data``, ``list_runs``) provide the
default filesystem implementation.  The ``RunStorage`` protocol is defined
in ``quodeq.services.ports`` — alternative backends (S3, database) should
implement that protocol and be injected at the call site.
"""

from __future__ import annotations

from pathlib import Path

from quodeq.core.types import DimensionResult
from quodeq.core.types.mappers import parse_dimension_result
from quodeq.data.fs.report_parser._evaluations import load_evaluations
from quodeq.data.fs.report_parser._evidence import load_evidence_map
from quodeq.data.fs.report_parser._repository import (
    build_repository_info as build_repository_info,
)
from quodeq.data.fs.report_parser._run_info import (
    RunInfo as RunInfo,
    parse_run_date,
    safe_read_dir as safe_read_dir,
)
from quodeq.data.fs.report_parser._run_lookup import (
    RunLookupCache as RunLookupCache,
    _get_previous_run_for_dimension as _get_previous_run_for_dimension,
    _make_caching_fetcher as _make_caching_fetcher,
)
from quodeq.shared.validation import validate_path_segment


def read_run_data(reports_root: Path, project: str, run_id: str) -> list[DimensionResult]:
    """Load all dimension evaluations and evidence for a single run.

    Example::

        dims = read_run_data(Path("/reports"), "my-project", "20260301")
    """
    validate_path_segment(project, run_id)
    run_dir = reports_root / project / run_id
    evaluations = load_evaluations(run_dir / "evaluation")
    evidence_map = load_evidence_map(run_dir / "evidence")

    dimensions: list[DimensionResult] = []
    for evaluation in evaluations:
        dimension = evaluation.get("dimension")
        evidence = evidence_map.get(dimension, {})
        merged = {
            **evaluation,
            "sourceFileCount": evidence.get("sourceFileCount"),
            "evidenceDate": evidence.get("date"),
            "discipline": evidence.get("discipline"),
        }
        dimensions.append(parse_dimension_result(merged))

    dimensions.sort(key=lambda item: item.dimension)
    return dimensions


def list_runs(reports_root: Path, project: str, *, limit: int = 100) -> list[RunInfo]:
    """Return runs for a project, sorted newest-first by date.

    When *limit* > 0 only the most recent *limit* runs are returned.

    Example::

        runs = list_runs(Path("/reports"), "my-project", limit=5)
    """
    validate_path_segment(project)
    project_dir = reports_root / project
    run_infos: list[RunInfo] = []
    for entry in safe_read_dir(project_dir):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        date_iso, date_label = parse_run_date(reports_root, project, entry.name)
        run_infos.append(RunInfo(run_id=entry.name, date_iso=date_iso, date_label=date_label))
    run_infos.sort(key=lambda r: (r.date_iso or "", r.run_id), reverse=True)
    if limit > 0:
        return run_infos[:limit]
    return run_infos
