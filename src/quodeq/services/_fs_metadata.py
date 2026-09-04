"""Metadata and detection helpers for the filesystem action provider.

Split (Task 13) into two sibling modules plus this orchestrator:
  - _fs_project_primitives.py: leaf metadata reads (_read_scan_summary,
    _check_path_exists, _extract_project_metadata, _read_repo_info,
    _local_repo_root).
  - _fs_discipline.py: language-stat and discipline-inference helpers
    (_read_language_stats, _read_discipline_from_eval,
    _find_discipline_in_run, _infer_discipline, _has_fingerprints).

Both are re-exported here: _local_repo_root is used by compare.py, and
_has_fingerprints/_infer_discipline are used by _fs_projects.py.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from quodeq.data.fs.standards_prefs import load_visible_standard_ids
from quodeq.services._wiring import RunInfo, read_run_data, summarize_dimensions
from quodeq.services._fs_project_primitives import _local_repo_root
from quodeq.services._fs_project_primitives import (  # noqa: F401 — re-export
    _check_path_exists,
    _extract_project_metadata,
    _read_repo_info,
    _read_scan_summary,
)
from quodeq.services._fs_discipline import (  # noqa: F401 — re-export
    _find_discipline_in_run,
    _has_fingerprints,
    _infer_discipline,
    _read_discipline_from_eval,
    _read_language_stats,
)
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from quodeq.core.scoring.params import ScoringParams


def _select_accumulated_dims(
    reports_root: Path, entry_name: str, runs: list[RunInfo], visible_set: set[str],
) -> tuple[dict[str, object], dict[str, Path], int | None]:
    """Pick each dimension's latest valid result across the default view runs.

    Same run-set selection as the accumulated Overview (complete-only,
    cancelled fallback, never failed or in_progress). Iterating ALL runs
    newest-first gave the card a different grade than the Overview whenever
    the newest run was cancelled/failed/in_progress.

    Each dimension may come from a DIFFERENT run (last valid run per
    dimension), so ``run_dir_by_dim`` remembers the source run's directory
    per dimension: the rescore in ``_compute_summary`` must use THAT run's
    evidence, not the newest run's.
    """
    from quodeq.services.scoring_view import select_default_view_runs  # noqa: PLC0415
    from quodeq.services._accumulated_data import _has_valid_score  # noqa: PLC0415

    project_dir = reports_root / entry_name
    view_runs = select_default_view_runs(runs)
    latest_by_dim: dict[str, object] = {}
    run_dir_by_dim: dict[str, Path] = {}
    files_count: int | None = None
    for run in view_runs:
        dims = read_run_data(reports_root, entry_name, run.run_id)
        for d in dims:
            # Same trust gate as the accumulated Overview (_has_valid_score):
            # skip a coverage-0 stub so the card falls through to a real
            # older run instead of showing the stub's inflated grade. Hidden
            # standards are skipped entirely: the Overview headline excludes
            # them, and a dimension the user cannot see must not move the
            # grade.
            if (d.dimension and d.dimension.lower() in visible_set
                    and d.dimension not in latest_by_dim and _has_valid_score(d)):
                latest_by_dim[d.dimension] = d
                validate_path_segment(run.run_id)
                run_dir_by_dim[d.dimension] = project_dir / run.run_id
            if files_count is None and d.source_file_count:
                files_count = d.source_file_count
    return latest_by_dim, run_dir_by_dim, files_count


def _apply_dismiss_delete_rescore(
    latest_by_dim: dict[str, object], run_dir_by_dim: dict[str, Path],
    dismissed: set, deleted: set, params: "ScoringParams",
) -> list:
    """Rescore each dimension from the run it was sourced from, if needed.

    Applies the project-wide dismiss/delete rescore so the card agrees with
    every other read path (detail/explorer/dashboard/trend all route through
    ``scored_run_dimensions``, i.e. read_run_data + ``_rescore_dimension``).
    ``read_run_data`` returns the raw scan; its SQL grade overlay reflects
    dismisses only when the run is freshly projected, and NEVER reflects
    deletions. Without this the project-card grade kept a stale, too-low
    value for any project with deletions (or dismissals on a
    not-yet-reprojected run) -- diverging from the score shown everywhere
    else.
    """
    if not (dismissed or deleted):
        return list(latest_by_dim.values())
    from quodeq.services.rescore import _rescore_dimension  # noqa: PLC0415

    return [
        _rescore_dimension(
            d, dismissed, deleted, params=params,
            run_dir=run_dir_by_dim.get(dim_name),
        )
        for dim_name, d in latest_by_dim.items()
    ]


def _compute_summary(
    reports_root: Path, entry_name: str, runs: list[RunInfo],
    params: "ScoringParams", visible_set: set[str],
) -> dict:
    try:
        latest_by_dim, run_dir_by_dim, files_count = _select_accumulated_dims(
            reports_root, entry_name, runs, visible_set)
        acc_dims = list(latest_by_dim.values())
        project_dir = reports_root / entry_name
        from quodeq.services.deleted import deleted_keys  # noqa: PLC0415
        from quodeq.services.dismissed import dismissed_keys  # noqa: PLC0415
        dismissed = dismissed_keys(project_dir)
        deleted = deleted_keys(project_dir)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        # Adapter errors only: a run/triage file that is missing, unreadable,
        # or malformed genuinely means "no data for the card".
        _logger.warning("Unreadable/malformed run metadata for card: %s", exc)
        return {"grade": None, "score": None, "files": None}
    # From here on it is business math over already-loaded data. It stays
    # OUTSIDE the try: a KeyError raised by a rescoring/summarising bug must
    # surface, not silently downgrade the card to {"grade": None}.
    acc_dims = _apply_dismiss_delete_rescore(
        latest_by_dim, run_dir_by_dim, dismissed, deleted, params)
    if not acc_dims:
        return {"grade": None, "score": None, "files": files_count}
    summary = summarize_dimensions(acc_dims, params)
    return {"grade": summary.overall_grade, "score": summary.numeric_average, "files": files_count}


def _summary_version(
    reports_root: Path, entry_name: str, runs: list[RunInfo], params: "ScoringParams",
) -> tuple[str, set[str]]:
    from quodeq.services.score_cache import accumulated_cache_version, per_run_versions  # noqa: PLC0415

    project_dir = reports_root / entry_name
    visible = load_visible_standard_ids(_local_repo_root(reports_root, entry_name))
    visible_set = set(visible)
    run_versions = per_run_versions(
        project_dir, entry_name, params, [(r.run_id, r.status) for r in runs])
    version = accumulated_cache_version(
        project_dir, params, run_versions, as_of=None, visible_dims=visible)
    return version, visible_set


def _compute_on_miss_summary(
    reports_root: Path, entry_name: str, runs: list[RunInfo],
    params: "ScoringParams", visible_set: set[str], version: str,
) -> tuple[str | None, float | None, int | None, bool]:
    """Compute-and-cache branch of ``_read_accumulated_summary``.

    Reached when *compute_on_miss* controls what happens on a cache miss.
    False (the default, used by the local projects-list path) never computes
    inline here -- callers only reach this branch via True (the shared-repo
    route, which has no warm-up engine, keeping the pre-warm-up behavior of
    computing inline on a miss) or the kill switch
    (``QUODEQ_DISABLE_SCORE_CACHE``), which always computes inline too since
    a disabled cache can never be filled by the warm-up engine.
    """
    from quodeq.services.score_cache import cached_project_summary  # noqa: PLC0415

    payload = cached_project_summary(
        entry_name, version,
        lambda: _compute_summary(reports_root, entry_name, runs, params, visible_set),
    )
    return payload["grade"], payload["score"], payload["files"], False


def _read_settled_or_pending_summary(
    entry_name: str, runs: list[RunInfo], version: str,
) -> tuple[str | None, float | None, int | None, bool]:
    """Read-only branch of ``_read_accumulated_summary``.

    Only a project with NO runs at all will never be picked up by the
    warm-up engine (``warm_project_summary`` has the same empty-runs gate),
    so a cache miss here would report pending forever -- report it settled
    instead. A project whose runs are all cancelled/in-progress (no
    "complete" run) is NOT special-cased here: ``warm_project_summary``
    computes a fallback grade for it too (cancelled fallback via
    ``select_default_view_runs``), so its cache must still be consulted
    below rather than assumed empty forever.
    """
    from quodeq.services.score_cache import read_project_summary_cached  # noqa: PLC0415

    if not runs:
        return None, None, None, False
    hit = read_project_summary_cached(entry_name, version)
    if hit is not None:
        return hit["grade"], hit["score"], hit["files"], False
    return None, None, None, True


def _read_accumulated_summary(
    reports_root: Path, entry_name: str, runs: list[RunInfo],
    params: "ScoringParams | None" = None, *, compute_on_miss: bool = False,
) -> tuple[str | None, float | None, int | None, bool]:
    """Compute accumulated grade and score across all runs. Returns (grade, score, files, pending).

    The card summary applies the same project-wide dismiss/delete rescore as
    every other read path (see the ``_rescore_dimension`` step in
    ``_compute_summary``), so the repositories-screen grade agrees with the
    Overview / explorer / trend. *params* (loaded from the saved formula when
    None) keeps the aggregate threshold labels and dimension weights
    consistent with the dashboard.

    The card also scopes to the project's visible-standards selection: the
    Overview headline averages only visible dimensions (the client filters
    the accumulated payload), so a card computed over ALL dimensions shows a
    different grade whenever a hidden dimension's score diverges. The
    selection is folded into the cache version so toggling a standard
    invalidates the cached card.

    See ``_compute_on_miss_summary`` and ``_read_settled_or_pending_summary``
    for the two branches' cache-hit/miss rationale.
    """
    if params is None:
        from quodeq.services import grade_formula  # noqa: PLC0415
        params = grade_formula.load_params()

    from quodeq.shared._env import score_cache_disabled  # noqa: PLC0415
    version, visible_set = _summary_version(reports_root, entry_name, runs, params)
    if compute_on_miss or score_cache_disabled():
        return _compute_on_miss_summary(reports_root, entry_name, runs, params, visible_set, version)
    return _read_settled_or_pending_summary(entry_name, runs, version)


def warm_project_summary(reports_root: Path, entry_name: str) -> None:
    """Compute-and-cache one project's card summary (warm-up engine entry).

    Computes whenever the project has ANY run, not just a "complete" one --
    a cancelled-only or in-progress-only project still gets a fallback grade
    via ``_compute_summary``'s ``select_default_view_runs`` cancelled
    fallback, so it must not be left permanently ungraded. Versions are
    status-stamped (``_summary_version`` -> ``per_run_versions``), so an
    in-progress run's cached row self-invalidates once it completes.
    """
    from quodeq.data.fs.report_parser.runs import list_runs  # noqa: PLC0415
    from quodeq.services import grade_formula  # noqa: PLC0415
    from quodeq.services.score_cache import cached_project_summary  # noqa: PLC0415

    runs = list_runs(reports_root, entry_name)
    if not runs:
        return
    params = grade_formula.load_params()
    version, visible_set = _summary_version(reports_root, entry_name, runs, params)
    cached_project_summary(
        entry_name, version,
        lambda: _compute_summary(reports_root, entry_name, runs, params, visible_set),
    )
