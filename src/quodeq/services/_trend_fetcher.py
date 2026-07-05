"""Shared cache-backed, dismiss-adjusted SCALAR trend fetcher.

Extracted from ``scoring/__init__.py`` so both the ``/scores`` endpoint
(``get_project_scores``) and the run-detail dashboard (``build_dashboard``)
can build their history trend / previous-score / stale computations off the
SAME fast, cache-backed, scalar-only fetcher instead of reading full run data
(violations, multi-MB) for every historical run.

This module depends only on leaf modules (``_cache``, ``score_cache``,
``ports``, ``rescore``) so it can be imported by both ``dashboard.py`` and
``scoring/__init__.py`` without a circular import.

Dependency injection: the scalar reader and the dismissed/deleted lookups are
parameters (defaulting to the real functions). ``scoring/__init__.py`` passes
its own module-level references so its monkeypatch-based tests keep working;
``dashboard.py`` uses the defaults.
"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Callable

from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.types import DimensionResult
from quodeq.services._cache import make_lru_dimension_fetcher
from quodeq.services.deleted import deleted_keys as _default_deleted_keys
from quodeq.services.dismissed import dismissed_keys as _default_dismissed_keys
from quodeq.services.ports import read_run_scalars as _default_read_run_scalars
from quodeq.services.rescore import _rescore_dimension
from quodeq.services.score_cache import make_cache_backed_fetcher, score_cache_version

_Fetcher = Callable[[str], list[DimensionResult]]


def make_rescoring_fetcher(
    reports_root: Path,
    project: str,
    params: ScoringParams = DEFAULT_PARAMS,
    *,
    base_fetcher: _Fetcher,
    dismissed_keys: Callable[[Path], set] = _default_dismissed_keys,
    deleted_keys: Callable[[Path], set] = _default_deleted_keys,
) -> _Fetcher:
    """Return a dimension fetcher that applies dismiss/delete rescore to results.

    Wraps *base_fetcher* (a full-data run-dimension fetcher) so consumers get
    dismiss-adjusted data. Identity when the project has no active
    dismissals/deletions.
    """
    project_dir = reports_root / project
    dismissed = dismissed_keys(project_dir)
    deleted = deleted_keys(project_dir)
    if not dismissed and not deleted:
        return base_fetcher

    def rescoring_fetcher(run_id: str) -> list[DimensionResult]:
        dims = base_fetcher(run_id)
        return [_rescore_dimension(d, dismissed, deleted, params=params) for d in dims]

    return rescoring_fetcher


def make_trend_fetcher(
    reports_root: Path,
    project: str,
    params: ScoringParams = DEFAULT_PARAMS,
    cacheable_run_ids: set[str] | None = None,
    *,
    max_history: int,
    base_fetcher_factory: Callable[[Path, str], _Fetcher],
    read_run_scalars: Callable[[Path, str, str], list[DimensionResult]] = _default_read_run_scalars,
    dismissed_keys: Callable[[Path], set] = _default_dismissed_keys,
    deleted_keys: Callable[[Path], set] = _default_deleted_keys,
) -> _Fetcher:
    """Return the dimension fetcher for the history trend / previous / stale path.

    Fast path (no active dismissals/deletions): read only per-run scalar grades
    via *read_run_scalars* through a fresh per-call LRU cache, so scalar
    (findings-less) results never collide with the shared full-data cache used
    for the selected run.

    Heavy path (dismissals/deletions active): wrap the findings-based rescoring
    fetcher with the read-through score cache. The cache version is a content
    hash of dismissals/deletions/params, so any change auto-invalidates.

    ``cacheable_run_ids`` restricts which runs the heavy-path cache may
    *persist*: only terminal (complete) runs are safe. An in-progress run's
    scalar set grows as dims finish, and the version hash can't see that, so
    persisting its partial set would strand a stale row. When ``None`` every run
    is cacheable (fast path persists nothing anyway).

    In-progress freshness: both paths read in-progress runs fresh every request.
    Fast path uses a per-call cache (re-read next request); heavy path's
    ``cacheable_run_ids`` guard makes in-progress runs compute-through without
    persisting. Stale-partial detection is preserved inside ``read_run_scalars``,
    which falls back to full ``read_run_data`` whenever the SQL scalar projection
    disagrees with the on-disk ``evaluation/*.json`` count.
    """
    project_dir = reports_root / project
    if dismissed_keys(project_dir) or deleted_keys(project_dir):
        base = make_rescoring_fetcher(
            reports_root, project, params=params,
            base_fetcher=base_fetcher_factory(reports_root, project),
            dismissed_keys=dismissed_keys, deleted_keys=deleted_keys,
        )
        version = score_cache_version(project_dir, params)
        is_cacheable = (
            None if cacheable_run_ids is None
            else (lambda rid: rid in cacheable_run_ids)
        )
        return make_cache_backed_fetcher(project, version, base, is_cacheable=is_cacheable)

    cache: OrderedDict = OrderedDict()
    return make_lru_dimension_fetcher(
        reports_root, project, cache, Lock(),
        max_history, reader=read_run_scalars,
    )
