"""Single-run scores: SQL-backed with a JSON-eval-file fallback.

Split from ``scoring/__init__.py`` to keep that file under the size
ratchet's 300-line cap. ``get_scores_raw``/``get_scores_slim`` stay
re-exported from there. ``_logger`` is threaded from the package
``__init__.py`` (not a fresh ``logging.getLogger`` here) -- imported after
that module's own ``_logger`` is already assigned, so this resolves against
the already-initialized part of that (still-loading) module; no true cycle.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.services.grade_formula import load_params
from quodeq.services.ports import StoreUnreadableError
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services._wiring import SQLiteStateStore, SqliteFindingsRepository
from quodeq.services.scoring._deps import ScoringDeps, _NO_DEPS
from quodeq.services.scoring._response_builders import (
    _build_response_from_eval_files,
    _build_response_from_grade_tables,
)
from quodeq.services.scoring import _logger
from quodeq.shared.validation import validate_path_segment


def _prefer_eval_rescore(deps: ScoringDeps, project_dir: Path, run_dir: Path) -> bool:
    """True when the eval-JSON rescore path should be used instead of the
    (possibly stale) SQL grade tables.

    The SQL grade tables are frozen per run and, on a stale projection,
    reflect only the dismissals already projected into THIS run's own findings
    table -- NOT project-wide dismissals/deletions that accrued later. So when
    the project has active dismissals/deletions AND this run has eval JSON to
    rescore from, defer to the eval-file path, which applies the project-wide
    dismiss set authoritatively via ``rescore_dimensions`` -- the SAME
    transform the accumulated view uses, so every per-run read agrees on the
    dismiss-adjusted score. Event-log-only runs (no eval JSON) can't be
    rescored that way; they keep the SQL path, whose ``_ensure_fresh``
    re-projection applies the dismissals directly to the findings table.
    """
    has_project_wide_filters = bool(
        (deps.dismissed_keys or dismissed_keys)(project_dir)
        or (deps.deleted_keys or deleted_keys)(project_dir)
    )
    eval_dir = run_dir / "evaluation"
    return (
        has_project_wide_filters
        and eval_dir.is_dir()
        and any(p.suffix == ".json" for p in eval_dir.iterdir())
    )


def _scores_from_sql_grade_tables(
    run_dir: Path, project: str, run_id: str, params, deps: ScoringDeps,
) -> dict | None:
    """Return the SQL-grade-tables response, or None to fall back to the
    eval-JSON path (no events.jsonl, empty grade tables, or an unreadable
    evaluation.db)."""
    try:
        repo = (deps.findings_repo_factory or SqliteFindingsRepository)(run_dir)
        repo.ensure_projected()
        store_factory = deps.grade_tables_factory or SQLiteStateStore
        store = store_factory(run_dir)
        if store.read_dimension_scores():
            return _build_response_from_grade_tables(
                run_dir, params=params, store_factory=store_factory,
            )
    except StoreUnreadableError:
        # evaluation.db is unreadable by this binary: it was written by a
        # newer Quodeq (SchemaVersionError, a DatabaseError subclass) or is
        # otherwise corrupt/half-written. Don't crash the score read; fall
        # back to the JSON eval files (schema-independent) so a downgraded
        # or upgrading install still works.
        _logger.warning(
            "Run %s/%s has an unreadable evaluation.db; serving scores "
            "from the JSON eval files instead of the SQL grade tables.",
            project, run_id,
        )
    return None


def get_scores_raw(
    reports_root: Path, project: str, run_id: str,
    deps: ScoringDeps | None = None,
) -> dict:
    """Return raw rescore dict for a single run (explorer detail compat).

    Tries SQL grade tables first (fast path for runs projected from
    events.jsonl). Falls back to reading the eval JSON files + applying
    rescore when SQL is empty — this is the case for older runs that
    pre-date the event-log scoring engine. Without this fallback, ~all
    pre-event-log runs returned an empty ``{dimensions: [], summary: {}}``
    payload, which made live-grade updates impossible for them: the dismiss
    POST returned no scores, the UI had nothing to apply.
    """
    validate_path_segment(project, run_id)
    d = deps or _NO_DEPS
    run_dir = reports_root / project / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    params = load_params()
    project_dir = reports_root / project

    # SQL path is meaningful only when events.jsonl exists. For older runs
    # without one, skip straight to the JSON-file fallback so we don't have
    # to wait on a no-op projection that will leave the grade tables empty.
    if not _prefer_eval_rescore(d, project_dir, run_dir) and (run_dir / "events.jsonl").is_file():
        sql_response = _scores_from_sql_grade_tables(run_dir, project, run_id, params, d)
        if sql_response is not None:
            return sql_response

    return _build_response_from_eval_files(
        reports_root, project, run_id, params=params, deps=deps,
    )


def get_scores_slim(
    reports_root: Path, project: str, run_id: str,
    deps: ScoringDeps | None = None,
) -> dict:
    """``get_scores_raw`` with finding bodies stripped for the run-scores route.

    The Explorer (the endpoint's only consumer) uses the response to overlay
    dismissal-aware scores onto the eval payload it fetched separately: it
    reads per-dimension/per-principle score + grade + totals, and uses each
    violation solely as a ``req|file|line`` identity key to filter dismissed
    findings out of the eval data. Returning full bodies made the response
    7+ MB on finding-heavy runs; the slim form carries the same information
    the merge needs at a fraction of the size. Compliance bodies are never
    read from this payload, so the list is emptied (counts live in totals).
    """
    raw = get_scores_raw(reports_root, project, run_id, deps=deps)
    slim_dims = []
    for dim in raw.get("dimensions", []) or []:
        slim_violations = [
            {"req": v.get("req"), "file": v.get("file"), "line": v.get("line")}
            for v in (dim.get("violations") or [])
        ]
        slim_dims.append({**dim, "violations": slim_violations, "compliance": []})
    return {**raw, "dimensions": slim_dims}
