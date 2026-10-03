"""One project's runs and the row-backed fetcher that grades them.

``/scores`` and the Compare screen build the same two blocks, the
accumulated view and the trend, from one fetcher over ``run_scalars``. This
module holds what they share: the fetcher's construction, the trend over the
history window, and ``ProjectRows``, the bundle a caller that needs no
findings (Compare) builds both blocks from without a single full read.

Fetchers are called through the ``_fetchers`` module attribute so tests can
``monkeypatch.setattr(_fetchers, "make_scoring_trend_fetcher", ...)`` and
have it take effect here.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from quodeq.core.run.state import RunState
from quodeq.core.scoring.params import ScoringParams
from quodeq.core.types import DimensionResult
from quodeq.services.accumulated import read_all_run_data, run_source_file_count
from quodeq.services.dashboard_trend import build_accumulated_trend
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services.grade_formula import load_params
from quodeq.services.scoring import _fetchers
from quodeq.services.scoring._accumulated_rows import (
    AccumulatedScope,
    build_accumulated_from_rows,
    run_rows,
    runs_as_of,
)
from quodeq.services.scoring._deps import ScoringDeps
from quodeq.services.scoring_view import select_default_view_runs, select_trend_runs
from quodeq.services.suppression_keys import SuppressionKeys
from quodeq.services.wiring import RunInfo, list_runs

_Fetcher = Callable[[str], list[DimensionResult]]


def make_row_fetcher(
    reports_root: Path, project: str, params: ScoringParams, all_runs: list[RunInfo],
    deps: ScoringDeps | None = None,
) -> _Fetcher:
    """The row-backed fetcher the trend and the accumulated block share.

    Only completed runs may be persisted to the score cache: an in-progress
    run's scalar set is still growing, and the cache version can't see that,
    so caching its partial set would strand a stale row (e.g. 1 of 6 dims)
    served forever after the run finishes. Every completed run is eligible:
    the accumulated walk may reach past the history window.
    """
    cacheable_run_ids = {r.run_id for r in all_runs if r.status is RunState.DONE}
    return _fetchers.make_scoring_trend_fetcher(
        reports_root, project, params=params, cacheable_run_ids=cacheable_run_ids, deps=deps,
    )


def resolve_trend(params: ScoringParams, all_runs: list[RunInfo], fetcher: _Fetcher) -> list[dict]:
    """Build the trend over the history window with the shared *fetcher*.

    Shared trend rule (scoring_view.select_trend_runs): cancelled/failed
    runs are excluded; their partial scores are misleading on the history
    chart. They remain in availableRuns so the UI can show them when the
    user asks for them explicitly."""
    history_runs = select_trend_runs(all_runs)[:_fetchers.max_history_runs()]
    return build_accumulated_trend(history_runs, fetcher, params=params)


@dataclass(frozen=True, slots=True)
class ProjectRows:
    """A project's runs (newest first), its grading rules and the fetcher over its rows."""

    reports_root: Path
    project: str
    params: ScoringParams
    keys: SuppressionKeys
    runs: list[RunInfo]
    fetcher: _Fetcher

    @classmethod
    def load(cls, reports_root: Path, project: str, deps: ScoringDeps | None = None) -> ProjectRows:
        """Read the project's runs and suppressions and build its fetcher."""
        project_dir = reports_root / project
        params = load_params()
        runs = list_runs(reports_root, project)
        keys = SuppressionKeys(dismissed_keys(project_dir), deleted_keys(project_dir))
        return cls(reports_root, project, params, keys, runs, make_row_fetcher(
            reports_root, project, params, runs, deps))

    def dated_rows(self, run_id: str) -> list[DimensionResult]:
        """The run's rows with ``evidence_date`` filled from the run listing.

        Stands in for the full read where findings are not needed: a row
        carries every scalar of its dimension, and the run's date is the
        dimension's evidence date (both come from the same report).
        """
        date = next((r.date_iso for r in self.runs if r.run_id == run_id), None)
        return [replace(d, evidence_date=d.evidence_date or date) for d in run_rows(self.fetcher)(run_id)]

    def latest_rows(self, as_of: str | None = None) -> dict[str, DimensionResult]:
        """Each dimension's newest valid row across the default-view runs, by name.

        The accumulated walk without the hydration step: rows carry the
        rescored score, grade and principles, which is all a headline needs.
        """
        eligible = select_default_view_runs(runs_as_of(self.runs, as_of))
        if not eligible:
            return {}
        latest, _prev, _prev_run = read_all_run_data(
            self.reports_root, self.project, eligible, get_run_data=run_rows(self.fetcher))
        return latest

    def source_file_count(self) -> int | None:
        """The newest graded run's source file count, from its rows or its evidence manifest."""
        for run in select_default_view_runs(self.runs):
            rows = run_rows(self.fetcher)(run.run_id)
            if not rows:
                continue
            counted = next((d.source_file_count for d in rows if d.source_file_count), None)
            return counted or run_source_file_count(self.reports_root / self.project / run.run_id)
        return None

    def accumulated(self, as_of: str | None = None) -> dict[str, Any]:
        """The accumulated dims + summary from rows alone; dimensions carry no findings."""
        scope = AccumulatedScope(self.reports_root, self.project, self.params, self.keys)
        payload, _complete = build_accumulated_from_rows(
            scope, runs_as_of(self.runs, as_of), self.fetcher, fetch_full=self.dated_rows)
        return payload

    def trend(self) -> list[dict]:
        """The trend over the history window."""
        return resolve_trend(self.params, self.runs, self.fetcher)
