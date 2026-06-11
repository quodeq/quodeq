"""Persistence for user-tuned grade formula parameters.

The file at ``~/.quodeq/grade_formula.json`` holds the camelCase dict shape
from ``params_to_dict``. Absent file means Q² defaults. A corrupt file logs
a warning and falls back to defaults rather than breaking every score read.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from quodeq.core.scoring.params import (
    DEFAULT_PARAMS,
    ScoringParams,
    params_from_dict,
    params_to_dict,
    validate_params,
)
from quodeq.shared.run_status import UnsupportedSchemaError, read_status

_logger = logging.getLogger(__name__)


def grade_formula_path() -> Path:
    """Location of the custom-params file (function so tests can monkeypatch)."""
    return Path.home() / ".quodeq" / "grade_formula.json"


def load_params() -> ScoringParams:
    """Return saved custom params, or Q² defaults when absent or unreadable."""
    path = grade_formula_path()
    if not path.is_file():
        return DEFAULT_PARAMS
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        params = params_from_dict(data)
    except (OSError, json.JSONDecodeError, AttributeError, KeyError, TypeError, ValueError) as exc:
        _logger.warning("Unreadable %s (%s); using Q2 default formula.", path, exc)
        return DEFAULT_PARAMS
    if validate_params(params):
        _logger.warning("Invalid params in %s; using Q2 default formula.", path)
        return DEFAULT_PARAMS
    return params


def save_params(params: ScoringParams) -> None:
    """Validate and persist custom params. Raises ValueError when invalid."""
    errors = validate_params(params)
    if errors:
        raise ValueError("; ".join(errors))
    path = grade_formula_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(params_to_dict(params), indent=2), encoding="utf-8")


def reset_params() -> None:
    """Remove the custom-params file (back to Q² defaults)."""
    grade_formula_path().unlink(missing_ok=True)


def is_custom() -> bool:
    """True when a custom-params file is in effect."""
    return grade_formula_path().is_file()


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

    Run ids are random UUIDs (see ``_cli_evaluation.run_id = uuid4()``), so a
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


def apply_to_all_runs(reports_root: Path) -> int:
    """Rescore every run that has an events.jsonl with the currently saved params.

    Legacy runs without an event log cannot be rescored and are skipped.
    Always clears the dashboard cache (even when nothing was rescored, e.g.
    when *reports_root* does not exist). Returns the number of runs rescored.
    """
    from quodeq.data.projection.grade_projector import recompute_grades  # noqa: PLC0415
    from quodeq.services.dashboard import clear_shared_dimension_cache  # noqa: PLC0415

    params = load_params()
    count = 0
    if reports_root.is_dir():
        for project_dir in sorted(p for p in reports_root.iterdir() if p.is_dir()):
            for run_dir in sorted(r for r in project_dir.iterdir() if r.is_dir()):
                if not (run_dir / "events.jsonl").is_file():
                    continue
                try:
                    recompute_grades(run_dir, params=params)
                    count += 1
                except Exception:  # noqa: BLE001 — one bad run must not block the rest
                    _logger.warning("Rescore failed for %s; skipping.", run_dir, exc_info=True)
    clear_shared_dimension_cache()
    return count


def preview_scores(
    reports_root: Path, project: str, params: ScoringParams,
) -> dict | None:
    """Recompute the project's latest event-log run in memory with *params*.

    Read-only: never writes evaluation.db. Returns None when the project has
    no run with an events.jsonl. The ``before`` numbers use the currently
    SAVED params (what the dashboard shows today); the ``after`` numbers use
    the candidate *params* being previewed.
    """
    from quodeq.data.projection.grade_projector import compute_run_grades  # noqa: PLC0415
    from quodeq.data.sqlite.state_store import SQLiteStateStore  # noqa: PLC0415
    from quodeq.services.scoring.projector_scoring import compute_run_score  # noqa: PLC0415

    project_dir = reports_root / project
    if not project_dir.is_dir():
        return None
    run_dirs = _event_log_runs(project_dir)
    if not run_dirs:
        return None
    run_dir = run_dirs[0]

    saved = load_params()
    store = SQLiteStateStore(run_dir)
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
