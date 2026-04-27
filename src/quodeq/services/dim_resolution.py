"""Single source of truth for which run/dim data should appear in which view.

See ``docs/dim-resolution-design.md`` for the full mental model. TL;DR:
dimensions are the unit users care about; runs are the artifact. Every
view that surfaces scoring data should consult this module so they all
tell one coherent story instead of disagreeing because each implements
its own filter rules in its own corner of the codebase.

The functions here return *provenance* — for any per-dim score we display,
the caller can answer "from which run, on what date, in what state". That
metadata is what makes a hybrid (newest-data-per-dim across runs) view
honest instead of misleading.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from quodeq.data.fs.report_parser import RunInfo, list_runs
from quodeq.shared.validation import validate_path_segment

# Run states that may carry trustworthy per-dim eval data. ``failed`` is
# excluded unconditionally — a failure means system error before or during
# scoring, so any eval files written are not to be trusted.
_TRUSTABLE_RUN_STATES: frozenset[str] = frozenset({"complete", "in_progress", "cancelled"})

_EVAL_GLOB = "*.json"


@dataclass(frozen=True, slots=True)
class DimResolution:
    """Provenance of a single dim's most recent trustworthy eval."""

    dim_id: str
    eval_path: Path
    run_id: str
    run_state: str  # one of _TRUSTABLE_RUN_STATES
    run_date_iso: str | None
    files_read: int
    overall_score: str | None
    overall_grade: str | None


def _load_eval(eval_path: Path) -> dict[str, Any] | None:
    """Read an eval/<dim>.json file. Returns None on missing or invalid JSON."""
    try:
        return json.loads(eval_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _is_trustworthy(eval_data: dict[str, Any] | None) -> bool:
    """A scored eval is trustworthy when the model actually inspected files.

    A zero-coverage eval (``filesRead == 0``) typically comes from
    ``_score_completed_evidence`` writing a stub at cancel time when no
    findings actually landed. The score derived from such a file isn't
    meaningful; we exclude it so it can't pollute the per-dim cards.
    """
    if not eval_data:
        return False
    files_read = eval_data.get("filesRead")
    return isinstance(files_read, int) and files_read > 0


def _trustworthy_eval_dims(evaluation_dir: Path) -> set[str]:
    """Return dim_ids in *evaluation_dir* whose eval files are trustworthy.

    Empty set if the directory is missing or no eval is trustworthy.
    """
    if not evaluation_dir.is_dir():
        return set()
    return {
        p.stem for p in evaluation_dir.glob(_EVAL_GLOB)
        if _is_trustworthy(_load_eval(p))
    }


def resolve_latest_per_dim(
    reports_root: Path, project: str, *, run_limit: int = 100,
) -> dict[str, DimResolution]:
    """For each dim with a trustworthy eval file, return the freshest one.

    Walks runs newest-first; for each (run, dim) pair, accepts the first
    one where:

      - the run's state is in ``_TRUSTABLE_RUN_STATES`` (``failed`` excluded)
      - ``evaluation/<dim>.json`` exists with ``filesRead > 0``

    The returned mapping is what every per-dim view (overview cards, the
    headline, etc.) should read from. The headline must compute itself as
    ``mean(card.overall_score for card in result.values())`` so cards and
    headline can never disagree by construction.
    """
    validate_path_segment(project)
    project_dir = reports_root / project
    if not project_dir.is_dir():
        return {}

    out: dict[str, DimResolution] = {}
    for run in list_runs(reports_root, project, limit=run_limit):
        if run.status not in _TRUSTABLE_RUN_STATES:
            continue
        eval_dir = project_dir / run.run_id / "evaluation"
        if not eval_dir.is_dir():
            continue
        for eval_path in eval_dir.glob(_EVAL_GLOB):
            dim_id = eval_path.stem
            if dim_id in out:
                continue  # already resolved from a newer run
            data = _load_eval(eval_path)
            if not _is_trustworthy(data):
                continue
            out[dim_id] = DimResolution(
                dim_id=dim_id,
                eval_path=eval_path,
                run_id=run.run_id,
                run_state=run.status,
                run_date_iso=run.date_iso,
                files_read=int(data["filesRead"]),
                overall_score=data.get("overallScore"),
                overall_grade=data.get("overallGrade"),
            )
    return out


def is_visible_in_history(reports_root: Path, project: str, run: RunInfo) -> bool:
    """A run is visible in the history table iff it has any trustworthy eval.

    Failed runs and runs whose eval files are all zero-coverage stubs are
    hidden because they have nothing useful to surface — a row with "—"
    in every column is just clutter.
    """
    if run.status not in _TRUSTABLE_RUN_STATES:
        return False
    eval_dir = reports_root / project / run.run_id / "evaluation"
    return bool(_trustworthy_eval_dims(eval_dir))


def is_eligible_for_chart_bar(
    reports_root: Path, project: str, run: RunInfo,
    *, configured_dims: Iterable[str],
) -> bool:
    """Stricter than history: only fully-scored runs get a chart bar.

    The score-history chart implies "snapshot of overall score at this
    point in time", which requires every configured dim to have actually
    contributed. Partial runs still appear in the table (with a marker)
    so users can drill in, but they don't pollute the trend line.

    ``in_progress`` runs are eligible if all their configured dims have
    finished scoring — the snapshot is just early.
    """
    if run.status not in {"complete", "in_progress"}:
        return False
    eval_dir = reports_root / project / run.run_id / "evaluation"
    scored = _trustworthy_eval_dims(eval_dir)
    return scored.issuperset(configured_dims)
