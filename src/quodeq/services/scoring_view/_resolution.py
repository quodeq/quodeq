"""I/O-bound resolvers — turn on-disk eval files into ``DimResolution``s.

This module is the *bridge* between the pure predicates in ``_states``
and the actual filesystem layout under ``reports/<project>/<run>/...``.
It stays narrow: read eval files, apply predicates, return models.

Anything that needs richer composition (e.g. computing the score-history
chart from these resolutions) lives in ``_buckets`` or in callers — not
here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from quodeq.data.fs.report_parser import RunInfo, list_runs
from quodeq.shared.validation import validate_path_segment

from ._models import DimResolution
from ._states import (
    is_eligible_for_default_view,
    is_trustable_run,
)

_EVAL_GLOB = "*.json"


# ---------------------------------------------------------------------------
# Eval file inspection helpers (private)
# ---------------------------------------------------------------------------

def _load_eval(eval_path: Path) -> dict[str, Any] | None:
    """Read an eval/<dim>.json file. Returns None on missing or malformed.

    Best-effort: any I/O or decode failure is swallowed. Callers iterate
    many files; one bad file shouldn't break the whole resolution.
    """
    try:
        return json.loads(eval_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _is_trustworthy_eval(eval_data: dict[str, Any] | None) -> bool:
    """A scored eval is trustworthy when the model actually inspected files.

    A zero-coverage eval (``filesRead == 0``) typically comes from
    ``_score_completed_evidence`` writing a stub at cancel time when no
    findings landed. The score derived from such a file isn't meaningful;
    we exclude it everywhere — cards, history, chart — so it can't
    pollute any user-facing aggregation.
    """
    if not isinstance(eval_data, dict):
        return False
    files_read = eval_data.get("filesRead")
    return isinstance(files_read, int) and files_read > 0


def _trustworthy_dims_in_run(evaluation_dir: Path) -> set[str]:
    """Return dim_ids in *evaluation_dir* whose eval files are trustworthy.

    Empty set if the directory is missing or no eval is trustworthy.
    Iterating glob + load_eval + predicate; cheap on the dim count
    (~10) but gets called once per run, so don't add per-call I/O on
    callers — they'd make this O(runs × dims) on every resolve call.
    """
    if not evaluation_dir.is_dir():
        return set()
    return {
        p.stem for p in evaluation_dir.glob(_EVAL_GLOB)
        if _is_trustworthy_eval(_load_eval(p))
    }


# ---------------------------------------------------------------------------
# resolve_latest_per_dim — the core resolver
# ---------------------------------------------------------------------------

def resolve_latest_per_dim(
    reports_root: Path,
    project: str,
    *,
    as_of: str | None = None,
    run_limit: int = 100,
) -> dict[str, DimResolution]:
    """For each dim with a trustworthy eval file, return the freshest one.

    Walks runs newest-first; for each ``(run, dim)`` pair, accepts the
    first one where:

      - the run is **eligible for default view** (``complete`` only) —
        stricter than ``is_trustable_run`` because in-progress and
        cancelled-run evals aren't promoted to the cards by default.
      - ``evaluation/<dim>.json`` exists with ``filesRead > 0``.
      - the run's date is on or before ``as_of`` (when provided).

    The ``as_of`` parameter implements "view as of day X" for the score-
    history chart: clicking a past day should resolve cards using only
    runs from that day or earlier, not future ones. ``None`` means "as
    of right now" (no upper bound).

    The returned mapping is what every per-dim view should read from.
    The headline must compute itself as ``mean(card.overall_score for
    card in result.values())`` so cards and headline can never disagree
    by construction.
    """
    validate_path_segment(project)
    project_dir = reports_root / project
    if not project_dir.is_dir():
        return {}

    out: dict[str, DimResolution] = {}
    for run in list_runs(reports_root, project, limit=run_limit):
        if not is_eligible_for_default_view(run.status):
            continue
        if as_of is not None and run.date_iso is not None and run.date_iso > as_of:
            # Run is newer than the requested cutoff — skip without
            # consuming any of its dims, regardless of eval contents.
            continue
        eval_dir = project_dir / run.run_id / "evaluation"
        if not eval_dir.is_dir():
            continue
        for eval_path in eval_dir.glob(_EVAL_GLOB):
            dim_id = eval_path.stem
            if dim_id in out:
                continue  # already resolved from a newer run
            data = _load_eval(eval_path)
            if not _is_trustworthy_eval(data):
                continue
            out[dim_id] = DimResolution(
                dim_id=dim_id,
                eval_path=eval_path,
                run_id=run.run_id,
                run_state=run.status,  # type: ignore[arg-type]
                run_date_iso=run.date_iso,
                files_read=int(data["filesRead"]),
                overall_score=data.get("overallScore"),
                overall_grade=data.get("overallGrade"),
            )
    return out


# ---------------------------------------------------------------------------
# is_visible_in_history — history-table row filter
# ---------------------------------------------------------------------------

def is_visible_in_history(
    reports_root: Path, project: str, run: RunInfo,
) -> bool:
    """Whether *run* should appear as a row in the history table.

    A run is visible when it's **trustable** (excludes ``failed``) AND
    has at least one trustworthy eval file. Failed runs are hidden
    unconditionally; runs whose eval files are all zero-coverage stubs
    (e.g. cancel-time scoring stubs) are also hidden because a row
    full of dashes is just clutter.

    Note: this is not the same as "successful run" — cancelled runs
    with real partial data DO appear in history, marked as ``partial``
    in the UI. A separate predicate (``is_successful_run``) governs
    the "natural finish" filter for use on the score-history chart.
    """
    if not is_trustable_run(run.status):
        return False
    eval_dir = reports_root / project / run.run_id / "evaluation"
    return bool(_trustworthy_dims_in_run(eval_dir))


# ---------------------------------------------------------------------------
# is_eligible_for_chart_bar — score-history chart filter
# ---------------------------------------------------------------------------

def is_eligible_for_chart_bar(
    reports_root: Path, project: str, run: RunInfo,
    *, configured_dims: Iterable[str],
) -> bool:
    """Whether *run* should appear as a bar on the score-history chart.

    Stricter than history visibility: only runs where **every configured
    dim** has a trustworthy eval qualify. The chart implies "snapshot of
    the project's overall score at this point in time", which requires
    every dim to have contributed; a partial run still appears in the
    history table (with a marker) but doesn't pollute the trend line.

    ``in_progress`` runs are eligible if all their configured dims have
    finished scoring — the snapshot is just early. ``cancelled`` is
    excluded because the bar implies the run finished its lifecycle, not
    just its dims.
    """
    if run.status not in ("complete", "in_progress"):
        return False
    eval_dir = reports_root / project / run.run_id / "evaluation"
    scored = _trustworthy_dims_in_run(eval_dir)
    return scored.issuperset(configured_dims)


__all__ = [
    "resolve_latest_per_dim",
    "is_visible_in_history",
    "is_eligible_for_chart_bar",
]
