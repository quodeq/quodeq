"""Injectable dependency bundle for the scoring reader (see ScoringDeps).

Leaf module: imports only ports/stdlib (under ``TYPE_CHECKING``, so there is
no runtime dependency at all), so it can be imported by any ``services``
module without pulling in ``services.scoring`` (and its package-init side
effects). ``services/scoring/_deps.py`` re-exports from here so the
in-package importers (``scoring/_rescoring.py``, ``scoring/_scores_raw.py``,
``scoring/_fetchers.py``, ``scoring/_response_builders.py``,
``scoring/_project_scores.py``, ``scoring/__init__.py``) keep resolving
unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from pathlib import Path

    from quodeq.core.types import DimensionResult
    from quodeq.data.ports.findings import FindingsRepository
    from quodeq.services.ports import GradeTablesReader


@dataclass(frozen=True)
class ScoringDeps:
    """Injectable dependency bundle for the scoring reader.

    A ``None`` field resolves to the production callable at call time, so
    the seam is purely additive: existing callers pass nothing and see no
    change. Tests construct a ``ScoringDeps`` with fakes instead of
    patching this module's attributes — the namespace-patch coupling is
    what made the previous decomposition attempt revert.

    ``base_fetcher_factory`` and ``max_history`` are the exception: the
    trend-fetcher leaf module (``_trend_fetcher.py``) has no production
    default for either (the former needs the non-leaf full-data fetcher;
    the latter is a caller-chosen history window size), so callers of
    ``make_trend_fetcher``/``_make_heavy_trend_fetcher`` must set them.
    """

    read_run_data: Callable | None = None
    read_run_scalars: Callable | None = None
    dismissed_keys: Callable | None = None
    deleted_keys: Callable | None = None
    cached_accumulated: Callable | None = None
    rescore_dimension: Callable | None = None
    rescore_runs_by_dimension: Callable | None = None
    recompute_summary: Callable | None = None
    findings_repo_factory: Callable[[Path], FindingsRepository] | None = None
    grade_tables_factory: Callable[[Path], GradeTablesReader] | None = None
    is_custom_formula: Callable[[], bool] | None = None
    base_fetcher_factory: Callable[[Path, str], Callable[[str], list[DimensionResult]]] | None = None
    max_history: int | None = None


_NO_DEPS = ScoringDeps()
