"""User-tuned grade formula: apply/preview orchestration.

The parameter file itself is owned by ``data/fs/grade_formula_store.py``;
the accessors are re-exported here because the API layer talks to services,
not to data.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from quodeq.core.scoring.params import ScoringParams
from quodeq.core.scoring.projector_scoring import compute_run_score
from quodeq.services.ports import GradeTablesReader
from quodeq.services.wiring import (  # noqa: F401 — grade_formula_store names are re-exported API
    SQLiteStateStore,
    UnsupportedSchemaError,
    clear_rescore_pending,
    compute_run_grades,
    grade_formula_path,
    is_custom,
    load_params,
    mark_rescore_pending,
    read_status,
    recompute_grades,
    rescore_marker_path,
    rescore_pending,
    reset_params,
    save_params,
)

_logger = logging.getLogger(__name__)


def _run_recency_key(run_dir: Path) -> tuple[int, str | float]:
    """Sort key for run ordering: started_at from status.json (codebase convention).

    Falls back to directory mtime for runs that pre-date status.json or whose
    status.json is missing/corrupt.  ISO timestamps sort lexically ==
    chronologically, so (1, iso_str) > (0, any_mtime) naturally.
    """
    try:
        status = read_status(run_dir) or {}
    except UnsupportedSchemaError:
        return (0, run_dir.stat().st_mtime)
    started_at = status.get("started_at")
    if started_at:
        return (1, started_at)
    return (0, run_dir.stat().st_mtime)


def _event_log_runs(project_dir: Path) -> list[Path]:
    """Run dirs under *project_dir* that have an events.jsonl, newest-first.

    Run ids are random UUIDs (see ``cli_evaluation.run_id = uuid4()``), so a
    name sort would not surface the most recent run.  Ordered by
    ``started_at`` from status.json (codebase convention); directory mtime is
    used as a fallback for legacy runs that lack status.json.  Using mtime
    alone is unreliable because WAL-mode SQLite creates/removes ``-wal``/
    ``-shm`` sidecars on reads, bumping the mtime of old run directories above
    genuinely newer ones.
    """
    return sorted(
        (r for r in project_dir.iterdir()
         if r.is_dir() and (r / "events.jsonl").is_file()),
        key=_run_recency_key, reverse=True,
    )


@dataclass(frozen=True)
class ApplyResult:
    """Outcome of a grade-formula apply across all runs.

    ``failed`` lists the run-dir names that could not be rescored (a locked
    or corrupt evaluation.db, etc.). A non-empty ``failed`` means the apply
    was PARTIAL: those runs keep their old-formula grades and disagree with
    their rescored siblings, so the caller must surface it rather than
    report a silent success.

    ``aborted`` is True when ``should_abort`` stopped the pass between runs.
    The runs before the stop were rewritten; the caller starts over.
    """
    rescored: int
    failed: list[str]
    aborted: bool = False


# Transient failures (a momentarily-locked evaluation.db while a background
# scoring thread writes) clear on their own, so a bounded retry recovers the
# common case before a run is reported failed.
_APPLY_RETRIES = 2
_APPLY_RETRY_SLEEP_S = 0.15


def _iter_event_log_runs(reports_root: Path) -> Iterator[Path]:
    """Yield every run dir under *reports_root* that has an events.jsonl.

    Legacy runs without an event log cannot be rescored and are skipped.
    """
    if not reports_root.is_dir():
        return
    for project_dir in sorted(p for p in reports_root.iterdir() if p.is_dir()):
        for run_dir in sorted(r for r in project_dir.iterdir() if r.is_dir()):
            if (run_dir / "events.jsonl").is_file():
                yield run_dir


def _recompute_with_retries(run_dir: Path, params: ScoringParams) -> bool:
    """Recompute *run_dir*'s grades, retrying transient failures.

    Returns True on success. On exhausting the retries, logs the failure
    itself and returns False -- the caller decides what to do with that.
    """
    for attempt in range(_APPLY_RETRIES + 1):
        try:
            recompute_grades(run_dir, params=params)
            return True
        except Exception:  # noqa: BLE001 — one bad run must not block the rest
            if attempt < _APPLY_RETRIES:
                time.sleep(_APPLY_RETRY_SLEEP_S)
                continue
            _logger.warning(
                "Rescore failed for %s after %d attempts; it will "
                "keep the old formula's grades.",
                run_dir, _APPLY_RETRIES + 1, exc_info=True,
            )
            return False
    return False


def apply_to_all_runs(
    reports_root: Path,
    *,
    progress: Callable[[int, int], None] | None = None,
    should_abort: Callable[[], bool] | None = None,
) -> ApplyResult:
    """Rescore every run that has an events.jsonl with the currently saved params.

    Returns an ``ApplyResult`` with the rescored count and the run-dir names
    that failed after retries: a partial apply is reported, not swallowed,
    so the UI can warn that some runs still show the old formula.

    *progress* gets ``(done, total)``: once with ``done=0`` after the run
    list is built (so ``total`` is known before the first recompute), then
    after every run. *should_abort* is checked before each run; True stops
    the pass there with ``aborted=True``. The dashboard cache is cleared on
    every exit (aborted and raising included), because even a partial pass
    has rewritten some runs.
    """
    from quodeq.services.dashboard import clear_shared_dimension_cache  # noqa: PLC0415

    try:
        params = load_params()
        run_dirs = list(_iter_event_log_runs(reports_root))
        return _rescore_runs(run_dirs, params, progress, should_abort)
    finally:
        clear_shared_dimension_cache()


def _rescore_runs(
    run_dirs: list[Path],
    params: ScoringParams,
    progress: Callable[[int, int], None] | None,
    should_abort: Callable[[], bool] | None,
) -> ApplyResult:
    """Rescore *run_dirs* in order, reporting progress and honoring an abort request."""
    total = len(run_dirs)
    rescored = 0
    failed: list[str] = []
    if progress is not None:
        progress(0, total)
    for done, run_dir in enumerate(run_dirs, start=1):
        if should_abort is not None and should_abort():
            return ApplyResult(rescored=rescored, failed=failed, aborted=True)
        if _recompute_with_retries(run_dir, params):
            rescored += 1
        else:
            failed.append(run_dir.name)
        if progress is not None:
            progress(done, total)
    return ApplyResult(rescored=rescored, failed=failed)


def preview_scores(
    reports_root: Path, project: str, params: ScoringParams,
    *, store_factory: Callable[[Path], GradeTablesReader] | None = None,
) -> dict | None:
    """Recompute the project's latest event-log run in memory with *params*.

    Read-only: never writes evaluation.db. Returns None when the project has
    no run with an events.jsonl. The ``before`` numbers use the currently
    SAVED params (what the dashboard shows today); the ``after`` numbers use
    the candidate *params* being previewed. *store_factory* lets callers
    inject a fake ``GradeTablesReader`` instead of a real SQLite file;
    defaults to ``SQLiteStateStore``.
    """
    project_dir = reports_root / project
    if not project_dir.is_dir():
        return None
    run_dirs = _event_log_runs(project_dir)
    if not run_dirs:
        return None
    run_dir = run_dirs[0]

    saved = load_params()
    store = (store_factory or SQLiteStateStore)(run_dir)
    before_dims = store.read_dimension_scores()
    before_overall = compute_run_score(before_dims, params=saved)

    _, after_dims = compute_run_grades(run_dir, params)
    after_overall = compute_run_score(after_dims, params=params)

    def _payload(dims: list[dict], overall: dict) -> dict:
        return {
            "overall": overall,
            "dimensions": [
                {"dimension": d["dimension"], "score": d["score"], "grade": d["grade"]}
                for d in sorted(dims, key=lambda x: x["dimension"] or "")
            ],
        }

    return {
        "project": project,
        "runId": run_dir.name,
        "before": _payload(before_dims, before_overall),
        "after": _payload(after_dims, after_overall),
    }
