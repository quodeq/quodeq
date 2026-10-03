"""Shared cache-backed, dismiss-adjusted SCALAR trend fetcher.

Both the ``/scores`` endpoint (``get_project_scores``) and the run-detail
dashboard (``build_dashboard``) build their history trend, previous-score and
stale computations off the SAME row-backed fetcher instead of reading full run
data (violations, multi-MB) for every historical run. The accumulated view
walks the same fetcher's ``rows`` for its winning runs (see
``scoring/_accumulated_rows``), so one bulk read of ``run_scalars`` serves a
whole ``/scores`` response.

Every run is served from ``run_scalars`` at its scoped version (params,
standards, the suppressions touching it). A miss reads the run once: from its
grade tables when no suppression touches it, through the findings rescore
otherwise, and persists the result when the run is terminal.

This module depends only on leaf modules (``_cache``, ``score_cache``,
``ports``, ``rescore``, ``scoring_deps``) so it can be imported by both
``dashboard.py`` and ``scoring/__init__.py`` without a circular import.
``ScoringDeps`` lives at ``quodeq.services.scoring_deps`` (a leaf outside
the ``scoring`` package), so importing it here at module load time does not
force ``quodeq.services.scoring`` to initialize first.

Dependency injection: the scalar reader, the dismissed/deleted lookups and the
full-data base-fetcher factory are bundled in a ``ScoringDeps`` (see
``scoring_deps.py``). A ``None`` field falls back to the real function;
``scoring/__init__.py`` passes its own module-level references so its
monkeypatch-based tests keep working; ``dashboard.py`` uses the defaults for
everything except ``base_fetcher_factory``, which has no leaf-level default
and must always be supplied.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Callable

from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.types import DimensionResult
from quodeq.services._accumulated_data import read_scalar_dimensions
from quodeq.services.scoring_deps import ScoringDeps, NO_DEPS
from quodeq.services.deleted import deleted_keys as _default_deleted_keys
from quodeq.services.dismissed import dismissed_keys as _default_dismissed_keys
from quodeq.services.wiring import load_suppression_rules, read_run_scalars as _default_read_run_scalars
from quodeq.services.rescore import rescore_dimension, with_hidden_counts
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
    dismiss-adjusted data, each dimension carrying how many findings the
    suppressions hid (``with_hidden_counts``). Identity when the project has
    no active dismissals/deletions. The suppression readers come from *deps*
    (production defaults when None or unset).
    """
    validate_path_segment(project)
    d = deps or NO_DEPS
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
        return [
            with_hidden_counts(d, rescore_dimension(d, keys, params=params, run_dir=run_dir), keys)
            for d in dims
        ]

    return rescoring_fetcher


def _make_version_for(
    project_dir: Path, project: str, inputs: VersionInputs,
    load_keys: Callable[[str], tuple | None], cacheable_run_ids: set[str] | None,
) -> Callable[[str], str]:
    """Per-run scoped version for the cache-backed trend fetcher.

    *inputs* is the params + suppression state every run's version hashes
    against. *load_keys* returns one run's persisted key sets (None when not
    persisted) and is consulted only when that run's version is not already
    in ``score_cache.memoized_run_version``: decoding a run's key blobs is
    the expensive part, and a warm process rarely needs it.
    """
    from quodeq.services.run_keys import read_run_key_sets  # noqa: PLC0415
    from quodeq.services.score_cache import (  # noqa: PLC0415
        memoized_run_version, open_score_cache, remember_run_version,
        run_scoped_version, store_run_keys,
    )

    state_fp = inputs.fingerprint
    keys_cache: dict[str, tuple] = {}

    def version_for(run_id: str) -> str:
        cacheable = cacheable_run_ids is None or run_id in cacheable_run_ids
        if cacheable:
            memoized = memoized_run_version(project_dir, run_id, state_fp)
            if memoized is not None:
                return memoized
        keys = keys_cache.get(run_id) or load_keys(run_id)
        if keys is None:
            keys = read_run_key_sets(project_dir / run_id)
            if cacheable:
                try:
                    with open_score_cache() as _c:
                        store_run_keys(_c, project, run_id, keys[0], keys[1])
                except (OSError, sqlite3.Error):
                    _logger.debug(
                        "Could not store run keys in score cache for %s/%s",
                        project, run_id, exc_info=True,
                    )
        keys_cache[run_id] = keys
        version = run_scoped_version(
            inputs.params, keys[0], keys[1], inputs.dismissed, inputs.deleted,
            standards=inputs.standards)
        if cacheable:
            remember_run_version(project_dir, run_id, state_fp, version)
        return version

    return version_for


def _require_trend_deps(deps: ScoringDeps) -> None:
    """Fail fast on the ``ScoringDeps`` field with no leaf-level default.

    ``base_fetcher_factory`` was a required keyword-only parameter of the
    pre-refactor ``make_trend_fetcher``, so a caller that omitted it got a
    ``TypeError`` at call time. The check keeps that contract now that it
    lives on ``deps`` instead.
    """
    if deps.base_fetcher_factory is None:
        raise TypeError("ScoringDeps.base_fetcher_factory is required for the trend fetcher")


def _make_row_trend_fetcher(
    reports_root: Path, project: str, params: ScoringParams,
    cacheable_run_ids: set[str] | None,
    deps: ScoringDeps,
) -> _Fetcher:
    """Wrap the findings-based rescoring fetcher with the read-through score
    cache. The cache version is a content hash of dismissals/deletions/
    params/standards, so any change auto-invalidates."""
    base = make_rescoring_fetcher(
        reports_root, project, params=params,
        base_fetcher=deps.base_fetcher_factory(reports_root, project), deps=deps,
    )
    base = _read_untouched_runs_as_scalars(reports_root, project, base, deps)
    version_for = _suppression_version_for(
        reports_root / project, project, params, cacheable_run_ids, deps,
    )
    is_cacheable = (
        None if cacheable_run_ids is None
        else (lambda rid: rid in cacheable_run_ids)
    )
    return make_cache_backed_fetcher(
        project, version_for, base, is_cacheable=is_cacheable, log=SHARED_LOG,
    )


def _read_untouched_runs_as_scalars(
    reports_root: Path, project: str, rescoring: _Fetcher, deps: ScoringDeps,
) -> _Fetcher:
    """Serve a run no dismissal or deletion touches from its scalar grades.

    The rescore returns such a run unchanged, so reading every finding to feed it
    is wasted; its grade tables answer for it (``read_scalar_dimensions``, which
    falls back to the full read when they cannot). Only the runs a suppression
    actually touches (by the same key intersection that versions them,
    ``run_scoped_version``) are read in full and rescored. Suppression rules
    match by pattern, not by key, so with any rule every run is rescored.
    """
    project_dir = reports_root / project
    if load_suppression_rules(project_dir):
        return rescoring
    from quodeq.services.run_keys import read_run_key_sets  # noqa: PLC0415
    from quodeq.services.score_cache import persisted_run_key_sets  # noqa: PLC0415
    from quodeq.services.suppression_keys import as_dismissed_keys  # noqa: PLC0415

    dismissed = as_dismissed_keys((deps.dismissed_keys or _default_dismissed_keys)(project_dir))
    deleted = (deps.deleted_keys or _default_deleted_keys)(project_dir)
    read_scalars = deps.read_run_scalars or _default_read_run_scalars

    def scalars(run_id: str) -> list[DimensionResult]:
        return read_scalar_dimensions(
            reports_root, project, run_id, scalar_reader=read_scalars, log=SHARED_LOG)

    if not dismissed and not deleted:
        return scalars

    def fetch(run_id: str) -> list[DimensionResult]:
        validate_path_segment(run_id)
        dismiss_keys, class_keys = (
            persisted_run_key_sets(project, run_id) or read_run_key_sets(project_dir / run_id))
        if dismissed.touching(dismiss_keys) or deleted & class_keys:
            return rescoring(run_id)
        return scalars(run_id)

    return fetch


def _suppression_version_for(
    project_dir: Path, project: str, params: ScoringParams,
    cacheable_run_ids: set[str] | None, deps: ScoringDeps,
) -> Callable[[str], str]:
    """Per-run cache version keyed on *params* plus the project's current
    dismissals and deletions (read through *deps*)."""
    from quodeq.services.score_cache import persisted_run_key_sets  # noqa: PLC0415
    dismissed = (deps.dismissed_keys or _default_dismissed_keys)(project_dir)
    deleted = (deps.deleted_keys or _default_deleted_keys)(project_dir)
    return _make_version_for(
        project_dir, project, VersionInputs.of(params, dismissed, deleted, project_dir),
        lambda rid: persisted_run_key_sets(project, rid), cacheable_run_ids,
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

    Every run is served from ``run_scalars`` through a
    :class:`~quodeq.services._score_cache_fetch.RowFetcher` (see
    ``_make_row_trend_fetcher``): a hit at the run's scoped version returns
    its rows; a miss reads the run's grade tables when no suppression touches
    it and rescores its findings otherwise, then persists the rows.

    ``cacheable_run_ids`` restricts which runs the cache may *persist*: only
    terminal (complete) runs are safe. An in-progress run's scalar set grows
    as dims finish, and the version hash can't see that, so persisting its
    partial set would strand a stale row. When ``None`` every run is
    cacheable. Non-cacheable runs are read fresh every request. Stale-partial
    detection is preserved inside ``read_scalar_dimensions``, which falls back
    to the full read whenever the SQL scalar projection disagrees with the
    on-disk ``evaluation/*.json`` set.

    ``deps.base_fetcher_factory`` has no leaf-level default;
    ``_require_trend_deps`` checks it up front.
    """
    _require_trend_deps(deps)
    return _make_row_trend_fetcher(reports_root, project, params, cacheable_run_ids, deps)
