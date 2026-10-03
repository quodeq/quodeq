"""Single-run scores: SQL-backed with a JSON-eval-file fallback.

Split from ``scoring/__init__.py`` to keep that file under the size
ratchet's 300-line cap. ``get_scores_raw``/``get_scores_slim`` stay
re-exported from there.
"""
from __future__ import annotations

import copy
import logging
from pathlib import Path

from quodeq.services.grade_formula import load_params
from quodeq.services.ports import StoreUnreadableError
from quodeq.services.score_cache import params_fingerprint
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services.wiring import (
    SQLiteStateStore, SqliteFindingsRepository, count_eval_files, evaluation_db_stamp,
    load_suppression_rules,
)
from quodeq.services.scoring._deps import ScoringDeps, NO_DEPS
from quodeq.services.scoring._response_builders import (
    build_response_from_eval_files,
    build_response_from_grade_tables,
)
from quodeq.shared.stamp_memo import StampCache, file_stamp, memoized_by_stamp
from quodeq.shared.validation import validate_path_segment
from quodeq.services.scoring.compliance_detail import defer_dimension_detail

_logger = logging.getLogger(__name__)

#: SQL grade-tables responses, per run and params, held while the run's
#: database and event log are unchanged. The run page, the detail refill and
#: the dimension eval all read the same run; the first pays, the rest copy.
_SQL_SCORES_CACHE = StampCache(name="run_scores_sql")


def _prefer_eval_rescore(deps: ScoringDeps, project_dir: Path, run_dir: Path) -> bool:
    """True when the eval-JSON rescore path should be used instead of the
    (possibly stale) SQL grade tables.

    The SQL grade tables are frozen per run and, on a stale projection,
    reflect only the dismissals already projected into THIS run's own findings
    table -- NOT project-wide dismissals/deletions that accrued later, and
    never the pattern suppression rules, which no projection applies. So when
    the project has any suppression state (dismissals, deletions or rules)
    AND this run has eval JSON to rescore from, defer to the eval-file path,
    which applies all of it via ``rescore_dimensions`` -- the SAME transform
    the accumulated view and the dimension eval use, so every per-run read
    agrees on the suppressed set and score. Event-log-only runs (no eval
    JSON) can't be rescored that way; they keep the SQL path, whose
    ``_ensure_fresh`` re-projection applies the dismissals directly to the
    findings table.
    """
    has_project_wide_filters = bool(
        (deps.dismissed_keys or dismissed_keys)(project_dir)
        or (deps.deleted_keys or deleted_keys)(project_dir)
        or (deps.load_suppression_rules or load_suppression_rules)(project_dir)
    )
    # strict=True: an eval dir that exists but can't be listed (a permissions
    # problem, say) must still raise here, not silently read as "no eval
    # files" -- this mirrors the OSError propagation the old inline
    # eval_dir.iterdir() call had.
    return has_project_wide_filters and (count_eval_files(run_dir, strict=True) or 0) > 0


def _scores_from_sql_grade_tables(
    run_dir: Path, project: str, run_id: str, params, deps: ScoringDeps,
) -> dict | None:
    """The SQL-grade-tables response, or None to fall back to the eval-JSON
    path (no events.jsonl, empty grade tables, or an unreadable
    evaluation.db).

    Memoized on the database's stamp and the event log's: the projection
    inside ``ensure_projected`` is what folds new events into the database,
    so a grown ``events.jsonl`` must miss even while the database is
    untouched. Injected *deps* bypass the memo; they are a test seam and may
    not read the files the stamp describes. Callers get their own copy.
    """
    if deps is not NO_DEPS:
        return _read_sql_grade_tables(run_dir, project, run_id, params, deps)
    db_stamp = evaluation_db_stamp(run_dir)
    if db_stamp is None:
        return _read_sql_grade_tables(run_dir, project, run_id, params, deps)
    stamp = (db_stamp, file_stamp(run_dir / "events.jsonl"))
    hit = memoized_by_stamp(
        f"{run_dir}|{params_fingerprint(params)}", stamp,
        lambda: _read_sql_grade_tables(run_dir, project, run_id, params, deps),
        cache=_SQL_SCORES_CACHE,
    )
    return copy.deepcopy(hit) if hit is not None else None


def _read_sql_grade_tables(
    run_dir: Path, project: str, run_id: str, params, deps: ScoringDeps,
) -> dict | None:
    try:
        repo = (deps.findings_repo_factory or SqliteFindingsRepository)(run_dir)
        repo.ensure_projected()
        store_factory = deps.grade_tables_factory or SQLiteStateStore
        store = store_factory(run_dir)
        if store.read_dimension_scores():
            return build_response_from_grade_tables(
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
    d = deps or NO_DEPS
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

    return build_response_from_eval_files(
        reports_root, project, run_id, params=params, deps=deps,
    )


def get_scores_slim(
    reports_root: Path, project: str, run_id: str,
    deps: ScoringDeps | None = None,
) -> dict:
    """``get_scores_raw`` with finding detail deferred, for the run-scores route.

    The Explorer overlays dismissal-aware scores onto the eval payload it
    fetched separately, matching violations by ``req|file|line``; the run
    page builds its worst-files table, hero navigation, report and fix plan
    from the same lists. Both read identity and scalar fields only, so the
    items go out without ``context``, ``snippet``, ``reason`` and
    ``reqRefs`` (most of a finding-heavy run's 7+ MB) and
    ``/compliance-detail?run=`` refills them on demand.
    """
    raw = get_scores_raw(reports_root, project, run_id, deps=deps)
    return {**raw, "dimensions": defer_dimension_detail(raw.get("dimensions") or [])}
