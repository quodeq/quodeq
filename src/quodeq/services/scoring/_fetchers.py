"""Dimension fetchers for the accumulated-rescore and trend paths.

Split from ``scoring/__init__.py`` to break the facade import cycle: this
module is a leaf (imports only siblings and outside-package modules, never
the package ``__init__``), so ``_project_scores.py`` can import it directly
instead of reaching back into the still-loading facade.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable

from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.types.dimension import DimensionResult
from quodeq.services._trend_fetcher import make_trend_fetcher
from quodeq.services.dashboard import _make_run_dimension_fetcher
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services._wiring import read_run_scalars
from quodeq.services.scoring._deps import ScoringDeps, _NO_DEPS
from quodeq.shared._env import env_int


def _max_history_runs() -> int:
    """Read max history runs from env at call time for lazy configuration."""
    return env_int("QUODEQ_MAX_HISTORY_RUNS", 100, minimum=1)


def _make_trend_fetcher(
    reports_root: Path, project: str,
    params: ScoringParams = DEFAULT_PARAMS,
    cacheable_run_ids: set[str] | None = None,
    deps: ScoringDeps | None = None,
) -> Callable[[str], list[DimensionResult]]:
    """Return the dimension fetcher for the trend chart.

    Thin seam over the shared :func:`make_trend_fetcher` factory. The scalar
    reader and suppression readers come from *deps* (production defaults
    when None), plus the shared full-data base-fetcher factory. See
    :func:`make_trend_fetcher` for the fast/heavy path and caching semantics.
    """
    d = deps or _NO_DEPS
    return make_trend_fetcher(
        reports_root, project, params=params, cacheable_run_ids=cacheable_run_ids,
        deps=replace(
            d,
            base_fetcher_factory=d.base_fetcher_factory or _make_run_dimension_fetcher,
            read_run_scalars=d.read_run_scalars or read_run_scalars,
            dismissed_keys=d.dismissed_keys or dismissed_keys,
            deleted_keys=d.deleted_keys or deleted_keys,
            max_history=_max_history_runs(),
        ),
    )
