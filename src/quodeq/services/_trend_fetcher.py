"""Shared cache-backed, dismiss-adjusted SCALAR trend fetcher.

Extracted from ``scoring/__init__.py`` so both the ``/scores`` endpoint
(``get_project_scores``) and the run-detail dashboard (``build_dashboard``)
can build their history trend / previous-score / stale computations off the
SAME fast, cache-backed, scalar-only fetcher instead of reading full run data
(violations, multi-MB) for every historical run.

This module depends only on leaf modules (``_cache``, ``score_cache``,
``ports``, ``rescore``, ``_scoring_deps``) so it can be imported by both
``dashboard.py`` and ``scoring/__init__.py`` without a circular import.
``ScoringDeps`` lives at ``quodeq.services._scoring_deps`` (a leaf outside
the ``scoring`` package), so importing it here at module load time does not
force ``quodeq.services.scoring`` to initialize first.

Dependency injection: the scalar reader, the dismissed/deleted lookups, the
full-data base-fetcher factory, and the trend-window size are bundled in a
``ScoringDeps`` (see ``_scoring_deps.py``). A ``None`` field falls back to the
real function; ``scoring/__init__.py`` passes its own module-level references
so its monkeypatch-based tests keep working; ``dashboard.py`` uses the
defaults for everything except ``base_fetcher_factory``/``max_history``,
which have no leaf-level default and must always be supplied.
"""
from __future__ import annotations

import logging
import sqlite3
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Callable

from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.types import DimensionResult
from quodeq.services._cache import DimensionCacheContext, make_lru_dimension_fetcher
from quodeq.services._scoring_deps import ScoringDeps, _NO_DEPS
from quodeq.services.deleted import deleted_keys as _default_deleted_keys
from quodeq.services.dismissed import dismissed_keys as _default_dismissed_keys
from quodeq.data.fs.report_parser.runs import read_run_scalars as _default_read_run_scalars
from quodeq.services._wiring import load_suppression_rules
from quodeq.services.rescore import _rescore_dimension
from quodeq.services.score_cache import VersionInputs, make_cache_backed_fetcher
from quodeq.services.suppression_keys import SuppressionKeys
from quodeq.shared.log_sink import SHARED_LOG
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)

_Fetcher = Callable[[str], list[DimensionResult]]


def make_rescoring_fetcher(
    reports_root: Path,
    project: str,
    params: ScoringParams = DEFAULT_PARAMS,
    *,
    base_fetcher: _Fetcher,
    deps: ScoringDeps | None = None,
) -> _Fetcher:
    """Return a dimension fetcher that applies dismiss/delete rescore to results.

    Wraps *base_fetcher* (a full-data run-dimension fetcher) so consumers get
    dismiss-adjusted data. Identity when the project has no active
    dismissals/deletions. The suppression readers come from *deps*
    (production defaults when None or unset).
    """
    validate_path_segment(project)
    d = deps or _NO_DEPS
    project_dir = reports_root / project
    dismissed = (d.dismissed_keys or _default_dismissed_keys)(project_dir)
    deleted = (d.deleted_keys or _default_deleted_keys)(project_dir)
    rules = load_suppression_rules(project_dir)
    # Rules count as suppression state; see scored_run_dimensions.
    if not dismissed and not deleted and not rules:
        return base_fetcher
    keys = SuppressionKeys(dismissed, deleted, rules)

    def rescoring_fetcher(run_id: str) -> list[DimensionResult]:
        dims = base_fetcher(run_id)
        # The fetched dims all belong to *run_id*, so that run's directory is
        # the evidence basis for the rescore.
        validate_path_segment(run_id)
        run_dir = project_dir / run_id
        return [_rescore_dimension(d, keys, params=params, run_dir=run_dir) for d in dims]

    return rescoring_fetcher


def _make_version_for(
    project_dir: Path, project: str, inputs: VersionInputs,
    load_keys: Callable[[], dict], cacheable_run_ids: set[str] | None,
) -> Callable[[str], str]:
    """Per-run scoped version for the cache-backed trend fetcher.

    *inputs* is the params + suppression state every run's version hashes
    against. *load_keys* returns the project's persisted key sets and runs
    at most once per fetcher, and only when some run's version is not
    already in ``score_cache.memoized_run_version``: decoding every run's
    key blobs is the expensive part, and a warm process rarely needs it.
    """
    from quodeq.services.run_keys import read_run_key_sets  # noqa: PLC0415
    from quodeq.services.score_cache import (  # noqa: PLC0415
        memoized_run_version, open_score_cache, remember_run_version,
        run_scoped_version, store_run_keys,
    )

    state_fp = inputs.fingerprint
    keys_cache: dict | None = None

    def version_for(run_id: str) -> str:
        nonlocal keys_cache
        cacheable = cacheable_run_ids is None or run_id in cacheable_run_ids
        if cacheable:
            memoized = memoized_run_version(project_dir, run_id, state_fp)
            if memoized is not None:
                return memoized
        if keys_cache is None:
            keys_cache = load_keys()
        keys = keys_cache.get(run_id)
        if keys is None:
            keys = read_run_key_sets(project_dir / run_id)
            keys_cache[run_id] = keys
            if cacheable:
                try:
                    with open_score_cache() as _c:
                        store_run_keys(_c, project, run_id, keys[0], keys[1])
                except (OSError, sqlite3.Error):
                    _logger.debug(
                        "Could not store run keys in score cache for %s/%s",
                        project, run_id, exc_info=True,
                    )
        version = run_scoped_version(
            inputs.params, keys[0], keys[1], inputs.dismissed, inputs.deleted)
        if cacheable:
            remember_run_version(project_dir, run_id, state_fp, version)
        return version

    return version_for


def _require_trend_deps(deps: ScoringDeps) -> None:
    """Fail fast on the two ``ScoringDeps`` fields with no leaf-level default.

    Both were required keyword-only parameters of the pre-refactor
    ``make_trend_fetcher``, so a caller that omitted either got a ``TypeError``
    at call time regardless of which path (fast/heavy) would have run. Called
    unconditionally, before path selection, to keep that contract now that
    both live on ``deps`` instead.
    """
    if deps.max_history is None:
        raise TypeError("ScoringDeps.max_history is required for the trend fetcher's fast path")
    if deps.base_fetcher_factory is None:
        raise TypeError("ScoringDeps.base_fetcher_factory is required for the heavy trend path")


def _make_heavy_trend_fetcher(
    reports_root: Path, project: str, params: ScoringParams,
    cacheable_run_ids: set[str] | None,
    deps: ScoringDeps,
) -> _Fetcher:
    """Wrap the findings-based rescoring fetcher with the read-through score
    cache. The cache version is a content hash of dismissals/deletions/
    params, so any change auto-invalidates."""
    project_dir = reports_root / project
    dismissed_keys = deps.dismissed_keys or _default_dismissed_keys
    deleted_keys = deps.deleted_keys or _default_deleted_keys
    base = make_rescoring_fetcher(
        reports_root, project, params=params,
        base_fetcher=deps.base_fetcher_factory(reports_root, project), deps=deps,
    )
    from quodeq.services.score_cache import load_run_keys_or_empty  # noqa: PLC0415
    dismissed = dismissed_keys(project_dir)
    deleted = deleted_keys(project_dir)

    version_for = _make_version_for(
        project_dir, project, VersionInputs.of(params, dismissed, deleted),
        lambda: load_run_keys_or_empty(project), cacheable_run_ids,
    )
    is_cacheable = (
        None if cacheable_run_ids is None
        else (lambda rid: rid in cacheable_run_ids)
    )
    return make_cache_backed_fetcher(
        project, version_for, base, is_cacheable=is_cacheable, log=SHARED_LOG,
    )


def make_trend_fetcher(
    reports_root: Path,
    project: str,
    params: ScoringParams = DEFAULT_PARAMS,
    cacheable_run_ids: set[str] | None = None,
    *,
    deps: ScoringDeps,
) -> _Fetcher:
    """Return the dimension fetcher for the history trend / previous / stale path.

    Fast path (no active dismissals/deletions): read only per-run scalar grades
    via *deps.read_run_scalars* through a fresh per-call LRU cache, so scalar
    (findings-less) results never collide with the shared full-data cache used
    for the selected run.

    Heavy path (dismissals/deletions active): see _make_heavy_trend_fetcher.

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

    ``deps.base_fetcher_factory`` (heavy path) and ``deps.max_history`` (fast
    path) have no leaf-level default -- ``_require_trend_deps`` checks both
    up front, before path selection, so omitting either raises regardless of
    which path would have run.
    """
    _require_trend_deps(deps)
    project_dir = reports_root / project
    dismissed_keys = deps.dismissed_keys or _default_dismissed_keys
    deleted_keys = deps.deleted_keys or _default_deleted_keys
    if dismissed_keys(project_dir) or deleted_keys(project_dir):
        return _make_heavy_trend_fetcher(
            reports_root, project, params, cacheable_run_ids, deps,
        )

    ctx = DimensionCacheContext(
        cache=OrderedDict(), lock=Lock(), max_size=deps.max_history,
        reader=deps.read_run_scalars or _default_read_run_scalars,
    )
    return make_lru_dimension_fetcher(reports_root, project, ctx)
