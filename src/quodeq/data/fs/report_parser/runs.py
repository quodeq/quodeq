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
from quodeq.data.fs.report_parser._date_utils import normalize_date
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

_DEFAULT_RUN_LIMIT = 100


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


def _read_run_status(run_dir: Path) -> str | None:
    """Read state from status.json if present. Returns the state string or None."""
    import json as _json  # noqa: PLC0415
    status_path = run_dir / "status.json"
    if not status_path.is_file():
        return None
    try:
        with status_path.open("r", encoding="utf-8") as fp:
            data = _json.load(fp)
    except (OSError, ValueError):
        return None
    state = data.get("state")
    return state if isinstance(state, str) else None


def list_runs(reports_root: Path, project: str, *, limit: int = _DEFAULT_RUN_LIMIT) -> list[RunInfo]:
    """Return runs for a project, sorted newest-first by date.

    Prefers the global ``index.db`` when it exists and has rows for *project*;
    otherwise falls back to the filesystem scan. Older runs created before the
    index existed remain readable via the filesystem fallback.

    When *limit* > 0 only the most recent *limit* runs are returned.

    Example::

        runs = list_runs(Path("/reports"), "my-project", limit=5)
    """
    from quodeq.data.sqlite.connection import INDEX_DB_FILENAME  # noqa: PLC0415
    from quodeq.data.sqlite.index_repository import SqliteRunIndex  # noqa: PLC0415
    from quodeq.shared._env import get_quodeq_root  # noqa: PLC0415

    quodeq_root = get_quodeq_root()
    if (quodeq_root / INDEX_DB_FILENAME).is_file():
        indexed = SqliteRunIndex(quodeq_root).list_runs(project=project, limit=limit)
        if indexed:
            return [_indexed_to_run_info(r) for r in indexed]

    return _list_runs_from_filesystem(reports_root, project, limit=limit)


_INDEX_STATE_TO_RUN_INFO_STATUS = {
    "running": "in_progress",
    "completed": "complete",
    "failed": "failed",
    "cancelled": "cancelled",
}


def _indexed_to_run_info(indexed) -> RunInfo:
    """Translate an IndexedRun to the RunInfo shape returned by list_runs."""
    # TODO: index-first path may report stale "in_progress" if the run process
    # crashed without recording a finished state; consider PID liveness check.
    parsed = normalize_date(indexed.started_at)
    if parsed is None:
        date_iso = indexed.started_at
        date_label = indexed.started_at
    else:
        date_iso, date_label = parsed
    status = _INDEX_STATE_TO_RUN_INFO_STATUS.get(indexed.state, "complete")
    return RunInfo(
        run_id=indexed.run_id,
        date_iso=date_iso,
        date_label=date_label,
        branch=indexed.branch,
        status=status,
    )


def _list_runs_from_filesystem(
    reports_root: Path, project: str, *, limit: int,
) -> list[RunInfo]:
    validate_path_segment(project)
    project_dir = reports_root / project
    run_infos: list[RunInfo] = []
    for entry in safe_read_dir(project_dir):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        run_dir = Path(entry.path)
        manifest_exists = (run_dir / "evidence" / "manifest.json").exists()
        if not manifest_exists:
            continue
        # Status precedence:
        #   1. Live process holding the PID → "in_progress" (dimmed "Running…" in UI)
        #   2. status.json state in {cancelled, failed} → pass through
        #   3. Otherwise → "complete" (historical, crashed, pre-.pid-era runs)
        from quodeq.services._external_jobs import resolve_external_pid  # noqa: PLC0415
        pid = resolve_external_pid(project_dir.name, entry.name, reports_root)
        if pid is not None:
            status = "in_progress"
        else:
            raw_state = _read_run_status(run_dir)
            status = raw_state if raw_state in ("cancelled", "failed") else "complete"
        date_iso, date_label = parse_run_date(reports_root, project, entry.name)
        run_infos.append(RunInfo(run_id=entry.name, date_iso=date_iso, date_label=date_label, status=status))
    run_infos.sort(key=lambda r: (r.date_iso or "", r.run_id), reverse=True)
    if limit > 0:
        return run_infos[:limit]
    return run_infos
