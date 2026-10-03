"""Metadata and detection helpers for the filesystem action provider.

Split into two sibling modules plus this orchestrator:
  - _fs_project_primitives.py: leaf metadata reads (check_path_exists,
    extract_project_metadata, read_repo_info, local_repo_root).
  - _fs_discipline.py: language-stat and discipline-inference helpers
    (read_language_stats, read_discipline_from_eval,
    find_discipline_in_run, infer_discipline, project_has_fingerprints).

Both are re-exported here: local_repo_root is used by compare.py, and
project_has_fingerprints/infer_discipline are used by fs_projects.py.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from quodeq.core.scoring.report_grades import summarize_dimensions
from quodeq.services.wiring import RunInfo, load_visible_standard_ids
from quodeq.services._fs_project_primitives import local_repo_root
from quodeq.services._fs_project_primitives import (  # noqa: F401 — re-export
    check_path_exists,
    extract_project_metadata,
    read_repo_info,
)
from quodeq.services._fs_discipline import (  # noqa: F401 — re-export
    find_discipline_in_run,
    project_has_fingerprints,
    infer_discipline,
    read_discipline_from_eval,
    read_language_stats,
)
from quodeq.shared.log_sink import SHARED_LOG

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from quodeq.core.scoring.params import ScoringParams
    from quodeq.services.scoring import ProjectRows


def _project_rows(
    reports_root: Path, entry_name: str, runs: list[RunInfo], params: "ScoringParams",
) -> "ProjectRows":
    """The project's row-backed fetcher over *runs*, graded under *params*."""
    from quodeq.services.deleted import deleted_keys  # noqa: PLC0415
    from quodeq.services.dismissed import dismissed_keys  # noqa: PLC0415
    from quodeq.services.scoring import ProjectRows, make_row_fetcher  # noqa: PLC0415
    from quodeq.services.suppression_keys import SuppressionKeys  # noqa: PLC0415

    project_dir = reports_root / entry_name
    keys = SuppressionKeys(dismissed_keys(project_dir), deleted_keys(project_dir))
    fetcher = make_row_fetcher(reports_root, entry_name, params, runs)
    return ProjectRows(reports_root, entry_name, params, keys, runs, fetcher)


def summarize_card(rows: "ProjectRows", visible_set: set[str]) -> dict:
    """The card's grade, score and file count from *rows* alone.

    Walks the same default-view runs as the accumulated Overview (done-only,
    cancelled fallback) over the row-backed fetcher, whose rows already carry
    the project-wide dismiss/delete rescore, so the card agrees with the
    Overview headline without reading a report. Hidden standards are left
    out: the Overview headline averages only visible dimensions, and a
    dimension the user cannot see must not move the grade.
    """
    latest = rows.latest_rows()
    files_count = rows.source_file_count()
    dims = [d for name, d in latest.items() if name.lower() in visible_set]
    if not dims:
        return {"grade": None, "score": None, "files": files_count}
    summary = summarize_dimensions(dims, rows.params)
    return {"grade": summary.overall_grade, "score": summary.numeric_average, "files": files_count}


def _compute_summary(
    reports_root: Path, entry_name: str, runs: list[RunInfo],
    params: "ScoringParams", visible_set: set[str],
) -> dict:
    """``summarize_card`` over the project's rows; an unreadable project is an empty card."""
    try:
        rows = _project_rows(reports_root, entry_name, runs, params)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        # Adapter errors only: a triage file that is missing, unreadable, or
        # malformed genuinely means "no data for the card". The fetcher
        # tolerates unreadable runs itself; a bug in the summarising math
        # below must surface, not silently empty the card.
        logger.warning("Unreadable/malformed run metadata for card: %s", exc)
        return {"grade": None, "score": None, "files": None}
    return summarize_card(rows, visible_set)


@dataclass(frozen=True, slots=True)
class _SummaryScope:
    """What a project-card summary is keyed and filtered by.

    ``version`` is the score-cache version folding the runs' status, the
    formula params, and the visible-standards selection; ``visible_set`` is
    that selection as lowercase dimension ids.
    """
    version: str
    visible_set: set[str]


def _summary_version(
    reports_root: Path, entry_name: str, runs: list[RunInfo], params: "ScoringParams",
) -> _SummaryScope:
    from quodeq.services.score_cache import accumulated_cache_version, per_run_versions  # noqa: PLC0415

    project_dir = reports_root / entry_name
    visible = load_visible_standard_ids(local_repo_root(reports_root, entry_name))
    visible_set = set(visible)
    run_versions = per_run_versions(
        project_dir, entry_name, params, [(r.run_id, r.status) for r in runs])
    version = accumulated_cache_version(
        params, run_versions, as_of=None, visible_dims=visible)
    return _SummaryScope(version, visible_set)


def _compute_on_miss_summary(
    reports_root: Path, entry_name: str, runs: list[RunInfo],
    params: "ScoringParams", scope: _SummaryScope,
) -> tuple[str | None, float | None, int | None, bool]:
    """Compute-and-cache branch of ``read_accumulated_summary``.

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
        entry_name, scope.version,
        lambda: _compute_summary(reports_root, entry_name, runs, params, scope.visible_set),
        log=SHARED_LOG,
    )
    return payload["grade"], payload["score"], payload["files"], False


def _read_settled_or_pending_summary(
    entry_name: str, runs: list[RunInfo], version: str,
) -> tuple[str | None, float | None, int | None, bool]:
    """Read-only branch of ``read_accumulated_summary``.

    Only a project with NO runs at all will never be picked up by the
    warm-up engine (``warm_project_summary`` has the same empty-runs gate),
    so a cache miss here would report pending forever -- report it settled
    instead. A project whose runs are all cancelled/running (no
    "done" run) is NOT special-cased here: ``warm_project_summary``
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


def read_accumulated_summary(
    reports_root: Path, entry_name: str, runs: list[RunInfo],
    params: "ScoringParams | None" = None, *,
    compute_on_miss: bool = False, cache_enabled: bool = True,
) -> tuple[str | None, float | None, int | None, bool]:
    """Compute accumulated grade and score across all runs. Returns (grade, score, files, pending).

    The card summary applies the same project-wide dismiss/delete rescore as
    every other read path (see the ``rescore_dimension`` step in
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

    *cache_enabled* is the resolved QUODEQ_DISABLE_SCORE_CACHE kill switch
    (default True): the provider composition resolves it once via
    ``score_cache_disabled()`` and passes it in.

    See ``_compute_on_miss_summary`` and ``_read_settled_or_pending_summary``
    for the two branches' cache-hit/miss rationale.
    """
    if params is None:
        from quodeq.services import grade_formula  # noqa: PLC0415
        params = grade_formula.load_params()

    scope = _summary_version(reports_root, entry_name, runs, params)
    if compute_on_miss or not cache_enabled:
        return _compute_on_miss_summary(reports_root, entry_name, runs, params, scope)
    return _read_settled_or_pending_summary(entry_name, runs, scope.version)


def warm_project_summary(reports_root: Path, entry_name: str) -> None:
    """Compute-and-cache one project's card summary (warm-up engine entry).

    Computes whenever the project has ANY run, not just a "done" one --
    a cancelled-only or running-only project still gets a fallback grade
    via ``_compute_summary``'s ``select_default_view_runs`` cancelled
    fallback, so it must not be left permanently ungraded. Versions are
    status-stamped (``_summary_version`` -> ``per_run_versions``), so an
    in-progress run's cached row self-invalidates once it completes.
    """
    from quodeq.services.wiring import list_runs  # noqa: PLC0415
    from quodeq.services import grade_formula  # noqa: PLC0415
    from quodeq.services.score_cache import cached_project_summary  # noqa: PLC0415

    runs = list_runs(reports_root, entry_name)
    if not runs:
        return
    params = grade_formula.load_params()
    scope = _summary_version(reports_root, entry_name, runs, params)
    cached_project_summary(
        entry_name, scope.version,
        lambda: _compute_summary(reports_root, entry_name, runs, params, scope.visible_set),
        log=SHARED_LOG,
    )
