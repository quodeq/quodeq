"""Read protocol over a run's SQL grade tables."""
from __future__ import annotations

from typing import Protocol

from quodeq.core.scoring.params import ScoringParams


class GradeTablesReader(Protocol):
    """Read seam over a run's SQL grade tables (dimension/principle scores).

    The concrete implementation is ``data.sqlite.state_store.SQLiteStateStore``;
    ``services.scoring`` accepts a ``Callable[[Path], GradeTablesReader]``
    factory so the response builder can be driven by a fake without a real
    SQLite file.
    """

    def read_dimension_scores(self) -> list[dict]: ...

    def read_principle_grades(self) -> list[dict]: ...

    def read_run_score_from_dim_scores(self, params: ScoringParams | None = None) -> dict: ...
