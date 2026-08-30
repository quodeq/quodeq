"""Injectable dependency bundle for the scoring reader (see ScoringDeps)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from pathlib import Path

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


_NO_DEPS = ScoringDeps()

