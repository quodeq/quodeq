"""Run discovery, date parsing, and report aggregation for filesystem reports.

The module-level functions (``read_run_data``, ``list_runs``, etc.) are the
filesystem implementation — there is no ``RunStorage`` protocol here. A
caller that needs a substitute injects a reader callable instead: see
``ScoringDeps.read_run_data`` (``services/scoring/_deps.py``),
``_trend_fetcher._default_read_run_scalars``, and
``_run_lookup._make_caching_fetcher``.
"""

from __future__ import annotations

from pathlib import Path

from quodeq.core.utils.io import resolve_child_dir
from quodeq.core.types import DimensionResult
from quodeq.data.mappers import parse_dimension_result
from quodeq.data.fs.report_parser._evaluations import load_evaluations
from quodeq.data.fs.report_parser._external_pid import resolve_external_pid
from quodeq.data.fs.report_parser._evidence import load_evidence_map
from quodeq.data.fs.report_parser._repository import (
    build_repository_info as build_repository_info,
)
from quodeq.data.fs.report_parser._run_info import (
    RunInfo as RunInfo,
    parse_run_date,
    safe_read_dir as safe_read_dir,
)
from quodeq.data.fs.report_parser.run_dates import project_run_dates
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
    # Resolve both segments by listing rather than joining, so neither name
    # is ever concatenated onto a path. A miss raises the same
    # FileNotFoundError callers already handle for an absent run.
    project_dir = resolve_child_dir(reports_root, project)
    resolved_run = resolve_child_dir(project_dir, run_id) if project_dir else None
    if resolved_run is None:
        raise FileNotFoundError(f"Run not found: {project}/{run_id}")
    run_dir = Path(resolved_run)
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


# Terminal status.json states → History status vocabulary. A terminal state is
# authoritative even when the run's PID is still alive: the cancel path flips
# status.json to ``cancelled`` immediately, but the subprocess keeps draining
# its subagents for a few seconds before it exits. Without this, a cancelled
# run reappears as "running" in History for the length of that drain.
_TERMINAL_STATE_TO_STATUS = {
    "done": "complete",
    "failed": "failed",
    "cancelled": "cancelled",
}


def list_runs(reports_root: Path, project: str, *, limit: int = _DEFAULT_RUN_LIMIT) -> list[RunInfo]:
    """Return runs for a project, sorted newest-first by date.

    When *limit* > 0 only the most recent *limit* runs are returned.

    Example::

        runs = list_runs(Path("/reports"), "my-project", limit=5)
    """
    validate_path_segment(project)
    # Resolve by listing, not by joining: the returned path comes from the
    # directory enumeration, so *project* is only ever compared. No project
    # directory means no runs, which is what a bad name produces too.
    resolved = resolve_child_dir(reports_root, project)
    if resolved is None:
        return []
    project_dir = Path(resolved)
    index_dates = project_run_dates(reports_root, project)
    run_infos: list[RunInfo] = []
    for entry in safe_read_dir(project_dir):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        run_dir = Path(entry.path)
        # A run is real when it has a manifest OR a status.json. Runs started
        # without a prescan never write evidence/manifest.json, and the SQLite
        # index (History) already accepts any run with a status.json — the two
        # enumerators must agree or the Overview 404s on runs History shows.
        is_run = (run_dir / "evidence" / "manifest.json").exists() \
            or (run_dir / "status.json").is_file()
        if not is_run:
            continue
        # Status precedence:
        #   1. status.json state is terminal (done/failed/cancelled) → honor it,
        #      even over a still-live PID (a cancelled run keeps draining after
        #      its state flips; it must not resurface as "running").
        #   2. Live process holding the PID → "in_progress" (dimmed "Running…" in UI)
        #   3. Otherwise → "complete" (historical, crashed, pre-.pid-era runs)
        raw_state = _read_run_status(run_dir)
        terminal_status = _TERMINAL_STATE_TO_STATUS.get(raw_state or "")
        if terminal_status is not None:
            status = terminal_status
        else:
            pid = resolve_external_pid(project_dir, entry.name)
            status = "in_progress" if pid is not None else "complete"
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
