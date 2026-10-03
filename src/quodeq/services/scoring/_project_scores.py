"""Full dashboard scores payload: accumulated + trend + available runs.

Split from ``scoring/__init__.py`` to keep that file under the size
ratchet's 300-line cap. ``get_project_scores`` stays re-exported from there.
The fetcher and the trend come from ``_project_rows``, which Compare
shares; it calls through the ``_fetchers`` module attribute so tests can
still ``monkeypatch.setattr(_fetchers, "make_scoring_trend_fetcher", ...)``.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quodeq.core.run.state import TERMINAL_STATES
from quodeq.core.scoring.params import ScoringParams
from quodeq.services.dashboard import make_run_dimension_fetcher
from quodeq.services.accumulated import compute_accumulated
from quodeq.services.grade_formula import is_custom, load_params
from quodeq.services.score_cache import (
    accumulated_cache_version,
    per_run_versions,
    suppression_state_fingerprint,
)
from quodeq.services.standards_version import standards_fingerprint
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services.suppression_keys import SuppressionKeys
from quodeq.shared.log_sink import SHARED_LOG
from quodeq.shared.stamp_memo import StampCache
from quodeq.services.wiring import find_children, list_runs, run_fingerprint
from quodeq.services.scoring._accumulated_rows import (
    EMPTY_ACCUMULATED,
    AccumulatedScope,
    build_accumulated_from_rows,
    runs_as_of,
)
from quodeq.services.scoring._project_rows import make_row_fetcher, resolve_trend
from quodeq.services.scoring._deps import ScoringDeps, NO_DEPS
from quodeq.services.scoring._rescoring import rescore_accumulated_with_coverage


@dataclass(frozen=True, slots=True)
class _ScoresRequest:
    """One ``get_project_scores`` call's inputs, shared by its accumulated steps."""

    reports_root: Path
    project: str
    as_of: str | None
    params: ScoringParams
    deps: ScoringDeps


def _compute_parent_payload(req: _ScoresRequest, rescore_complete: list[bool]) -> dict:
    """A parent project's accumulated dims + summary, folding in its children.

    Children's runs and suppressions are outside the project's rows, so
    parents keep the full-read path and rescore. Coverage lands in
    *rescore_complete* (a 1-element list used as an outparam) so the caller's
    cache-eligibility check can see it.
    """
    acc = compute_accumulated(
        str(req.reports_root), req.project, req.as_of, params=req.params, log=SHARED_LOG,
    )
    if acc is None:
        acc = dict(EMPTY_ACCUMULATED)
    payload, complete = rescore_accumulated_with_coverage(
        acc, req.reports_root, req.project, params=req.params, deps=req.deps,
    )
    rescore_complete[0] = complete
    return payload


def _compute_accumulated_payload(
    req: _ScoresRequest, rescore_complete: list[bool], all_runs: list, fetcher, keys: SuppressionKeys,
) -> dict:
    """The accumulated dims + summary from the project's score-cache rows.

    Shares *fetcher* with the trend, so every run is graded once per request
    and the winning runs are the only full reads (through
    ``deps.base_fetcher_factory``, the same full-data reader the trend
    rescores from).
    """
    scope = AccumulatedScope(req.reports_root, req.project, req.params, keys)
    fetch_full = (req.deps.base_fetcher_factory or make_run_dimension_fetcher)(req.reports_root, req.project)
    payload, complete = build_accumulated_from_rows(
        scope, runs_as_of(all_runs, req.as_of), fetcher, fetch_full=fetch_full)
    rescore_complete[0] = complete
    return payload


def _state_fingerprint(req: _ScoresRequest, keys: SuppressionKeys) -> str:
    return suppression_state_fingerprint(
        req.params, keys.dismissed, keys.deleted,
        standards=standards_fingerprint(req.reports_root / req.project))


def _resolve_accumulated(
    req: _ScoresRequest, rescore_complete: list[bool], keys: SuppressionKeys, all_runs: list, fetcher,
) -> dict:
    """The accumulated dims + summary: from rows for a plain project, full reads for a parent.

    Built on every call; ``_PAYLOADS`` memoizes the whole payload above this.
    A persisted accumulated slot used to sit here too, but with the rows
    cached per run it saved nothing a warm process could measure.
    """
    if find_children(req.reports_root, req.project):
        # Parent aggregation pulls child projects' dismissals/runs into the
        # payload, which the project-scoped stamp can't see.
        return _compute_parent_payload(req, rescore_complete)
    return _compute_accumulated_payload(req, rescore_complete, all_runs, fetcher, keys)


def _empty_project_scores(scoring_meta: dict) -> dict[str, Any]:
    return {
        "accumulated": dict(EMPTY_ACCUMULATED),
        "trend": [],
        "availableRuns": [],
        "scoring": scoring_meta,
    }


#: One full payload per project (latest only); a decoded payload can be tens
#: of MB, so the bound is a handful of projects, like the stale slots.
PAYLOAD_MEMO_MAX = 8
_PAYLOADS = StampCache(max_entries=PAYLOAD_MEMO_MAX, name="project_scores.payloads")


def _payload_stamp(
    req: _ScoresRequest, all_runs: list, run_versions: list[tuple], keys: SuppressionKeys, custom: bool,
) -> tuple:
    """Everything the payload depends on: the accumulated version (params,
    per-run content), the project's suppression state, each run's status,
    the formula flag, and the files of every run still in flight (its cache
    version only sees suppressions that touch it, yet its trend point moves
    with every dimension it scores)."""
    project_dir = req.reports_root / req.project
    in_flight = tuple(
        (r.run_id, run_fingerprint(project_dir / r.run_id))
        for r in all_runs if r.status not in TERMINAL_STATES
    )
    return (
        accumulated_cache_version(req.params, run_versions, req.as_of),
        _state_fingerprint(req, keys),
        tuple((r.run_id, str(r.status)) for r in all_runs),
        in_flight,
        custom,
    )


def _build_project_scores(
    req: _ScoresRequest, all_runs: list, scoring_meta: dict, keys: SuppressionKeys,
) -> tuple[dict[str, Any], bool]:
    """The payload and whether its rescore covered every dimension."""
    # The rescore-coverage flag rides in a cell so the memo gate can see it:
    # a payload whose rescore missed dimensions must be served but never
    # memoized (its stamp can't self-invalidate).
    rescore_complete = [True]
    fetcher = make_row_fetcher(req.reports_root, req.project, req.params, all_runs, req.deps)
    accumulated = _resolve_accumulated(req, rescore_complete, keys, all_runs, fetcher)
    trend = resolve_trend(req.params, all_runs, fetcher)
    payload = {
        "accumulated": accumulated,
        "trend": trend,
        "availableRuns": [
            {"runId": r.run_id, "dateLabel": r.date_label, "status": r.status}
            for r in all_runs
        ],
        "scoring": scoring_meta,
    }
    return payload, rescore_complete[0]


def get_project_scores_stamped(
    reports_root: Path, project: str, as_of: str | None = None,
    deps: ScoringDeps | None = None,
) -> tuple[dict[str, Any] | None, tuple | None]:
    """The full scores payload for the dashboard, with the stamp it was built under.

    Returns a dict with:
      - accumulated: { dimensions, summary } (same shape as /accumulated endpoint)
      - trend: [{ runId, dateISO, ... }] (same shape as dashboard.trend)
      - availableRuns: [{ runId, dateLabel, status }]
    All scores have dismissals applied server-side.

    The payload is reused while the stamp holds, so an unchanged project
    costs the stamp (run listing, per-run versions) and no cache decode,
    trend rebuild or rescore. The stamp is None when there is nothing to
    memoize: no project, no runs, or a parent project (its payload folds in
    children the stamp cannot see).
    """
    if not (reports_root / project).exists():
        return None, None
    d = deps or NO_DEPS
    params = load_params()
    # How the numbers were produced, not what they are. A tuned formula moves
    # every score at once and leaves no other trace -- findings and runs are
    # unchanged -- so the Overview has to be able to say so next to the grade.
    scoring_meta = {"customFormula": (d.is_custom_formula or is_custom)()}
    all_runs = list_runs(reports_root, project)
    if not all_runs:
        return _empty_project_scores(scoring_meta), None
    req = _ScoresRequest(reports_root, project, as_of, params, d)
    project_dir = reports_root / project
    keys = SuppressionKeys(dismissed_keys(project_dir), deleted_keys(project_dir))
    # A parent's payload folds in children the stamp cannot see; an as-of
    # payload is frozen client-side already. Only the latest payload of a
    # plain project is worth an entry.
    if as_of is not None or find_children(reports_root, project):
        return _build_project_scores(req, all_runs, scoring_meta, keys)[0], None
    run_versions = per_run_versions(project_dir, project, params,
                                    [(r.run_id, r.status) for r in all_runs], keys=keys)
    stamp = _payload_stamp(req, all_runs, run_versions, keys, scoring_meta["customFormula"])
    key = f"{reports_root}|{project}"
    hit = _PAYLOADS.get(key, stamp)
    if hit is not None:
        return hit, stamp  # type: ignore[return-value]
    payload, complete = _build_project_scores(req, all_runs, scoring_meta, keys)
    if complete:
        _PAYLOADS.put(key, stamp, payload)
    return payload, stamp


def get_project_scores(
    reports_root: Path, project: str, as_of: str | None = None,
    deps: ScoringDeps | None = None,
) -> dict[str, Any] | None:
    """The full scores payload for the dashboard (see ``get_project_scores_stamped``)."""
    return get_project_scores_stamped(reports_root, project, as_of, deps)[0]
