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
    # For event-log runs, the SQL grade tables (rewritten on dismiss and on a
    # grade-formula Apply) are the source of truth; overlay them so every
    # read-side consumer — run detail, accumulated overview, trend, project
    # cards — agrees with the run-detail SQL grades. Legacy runs (no
    # events.jsonl) keep their frozen eval-time grades.
    from quodeq.data.fs.report_parser._sql_grade_overlay import (  # noqa: PLC0415
        overlay_sql_grades,
    )
    return overlay_sql_grades(run_dir, dimensions)


def read_run_scalars(reports_root: Path, project: str, run_id: str) -> list[DimensionResult]:
    """Load a run's per-dimension SCALARS (score/grade/principles) only.

    Fast path for the dashboard trend and accumulated carry-forward, which need
    only ``overall_score`` / ``overall_grade`` per dimension — not the full
    findings.  Reads the authoritative SQL grade tables directly instead of
    parsing the evaluation JSON, then falls back to :func:`read_run_data`
    whenever the SQL tables can't faithfully reproduce the overlaid result:
    legacy run (no ``events.jsonl``) or no ``evaluation.db``; SQLite disabled or
    db unreadable; empty grade tables; a NULL SQL score (overlay would keep the
    eval-time score); or the SQL dim count != the on-disk ``evaluation/*.json``
    count (partial projection).  Returned dimensions carry empty findings.
    """
    validate_path_segment(project, run_id)
    run_dir = reports_root / project / run_id

    from quodeq.data.fs.report_parser._evidence_sqlite import has_evaluation_db  # noqa: PLC0415
    from quodeq.shared._env import sqlite_disabled  # noqa: PLC0415

    if (
        sqlite_disabled()
        or not has_evaluation_db(run_dir)
        or not (run_dir / "events.jsonl").is_file()
    ):
        return read_run_data(reports_root, project, run_id)

    import sqlite3  # noqa: PLC0415

    from quodeq.core.types.report import PrincipleGrade  # noqa: PLC0415
    from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository  # noqa: PLC0415
    from quodeq.data.sqlite.state_store import SQLiteStateStore  # noqa: PLC0415

    try:
        SqliteFindingsRepository(run_dir).ensure_projected()
        store = SQLiteStateStore(run_dir)
        dim_rows = store.read_dimension_scores()
        principle_rows = store.read_principle_grades()
    except sqlite3.DatabaseError:
        return read_run_data(reports_root, project, run_id)

    if not dim_rows:
        return read_run_data(reports_root, project, run_id)

    if any(r.get("score") is None for r in dim_rows):
        return read_run_data(reports_root, project, run_id)

    eval_dir = run_dir / "evaluation"
    on_disk = (
        sum(1 for p in eval_dir.iterdir() if p.suffix == ".json")
        if eval_dir.is_dir() else 0
    )
    if on_disk and len(dim_rows) != on_disk:
        return read_run_data(reports_root, project, run_id)

    # No eval-time grade fallback here (unlike overlay_sql_grades): the fast
    # path doesn't read the JSON, and a projected dim past the NULL-score
    # guard always carries a real grade label ("Insufficient" or better),
    # never "".
    principles_by_dim: dict[str, list[PrincipleGrade]] = {}
    for r in principle_rows:
        principles_by_dim.setdefault(r["dimension"], []).append(PrincipleGrade(
            principle=r["principle_id"],
            score=f'{r["score"]}/10' if r.get("score") is not None else None,
            grade=r.get("grade"),
        ))

    dimensions = [
        DimensionResult(
            dimension=r["dimension"],
            overall_score=f'{r["score"]}/10',
            overall_grade=r.get("grade"),
            principles=principles_by_dim.get(r["dimension"], []),
        )
        for r in dim_rows
    ]
    dimensions.sort(key=lambda d: d.dimension)
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
    if not isinstance(data, dict):
        return None
    state = data.get("state")
    return state if isinstance(state, str) else None


def list_runs(reports_root: Path, project: str, *, limit: int = _DEFAULT_RUN_LIMIT) -> list[RunInfo]:
    """Return runs for a project, sorted newest-first by date.

    When *limit* > 0 only the most recent *limit* runs are returned.

    Example::

        runs = list_runs(Path("/reports"), "my-project", limit=5)
    """
    validate_path_segment(project)
    project_dir = reports_root / project
    from quodeq.services.run_dates import project_run_dates  # noqa: PLC0415
    index_dates = project_run_dates(reports_root, project)
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
        cached = index_dates.get(entry.name)
        if cached is not None:
            date_iso, date_label = cached
        else:
            date_iso, date_label = parse_run_date(reports_root, project, entry.name)
        run_infos.append(RunInfo(run_id=entry.name, date_iso=date_iso, date_label=date_label, status=status))
    run_infos.sort(key=lambda r: (r.date_iso or "", r.run_id), reverse=True)
    if limit > 0:
        return run_infos[:limit]
    return run_infos
