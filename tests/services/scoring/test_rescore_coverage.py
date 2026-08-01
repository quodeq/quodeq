"""Rescore coverage: a partial rescore must be flagged so it is never persisted.

Regression: `_rescore_runs_by_dimension` silently treats a dimension missing
from the run read as "keep the raw score". When the run-dimension fetcher
served a partial dim list (1 of 6 dims frozen in the process LRU mid-run),
only that one dimension was rescored, and the half-rescored accumulated
payload was cached under a version hash identical to the complete payload's,
so the Overview served raw baked scores forever while the detail pages showed
the dismiss-adjusted ones.
"""
from __future__ import annotations

from pathlib import Path

import quodeq.services.scoring as scoring
from quodeq.services.scoring import (
    _dims_expecting_rescore,
    _rescore_accumulated_with_coverage,
)


def _acc(dims):
    return {"project": "proj", "dimensions": dims, "summary": {}}


def _dim(name, run_id="r1", score="5.0/10"):
    return {"dimension": name, "runId": run_id, "overallScore": score}


def test_dims_expecting_rescore_needs_a_source_run():
    dims = [
        _dim("security"),
        {"dimension": "performance"},  # no runId -> nothing to rescore from
        {"dimension": "", "runId": "r1"},
    ]
    assert _dims_expecting_rescore(dims) == {"security"}


def test_no_suppressions_is_complete():
    deps = scoring.ScoringDeps(
        dismissed_keys=lambda pdir: set(), deleted_keys=lambda pdir: set(),
    )
    payload, complete = _rescore_accumulated_with_coverage(
        _acc([_dim("security")]), Path("/reports"), "proj", deps=deps,
    )
    assert complete is True
    assert payload["dimensions"] == [_dim("security")]


def test_full_coverage_is_complete():
    deps = scoring.ScoringDeps(
        dismissed_keys=lambda pdir: {("R1", "a.py", 1)},
        deleted_keys=lambda pdir: set(),
        rescore_runs_by_dimension=lambda dims, root, project, dismissed, deleted=None, params=None: {
            "security": {"overallScore": "7.5/10", "overallGrade": "Good"},
            "performance": {"overallScore": "8.2/10", "overallGrade": "Good"},
        },
        recompute_summary=lambda dims, summary, params=None: summary,
    )
    payload, complete = _rescore_accumulated_with_coverage(
        _acc([_dim("security"), _dim("performance")]), Path("/reports"), "proj", deps=deps,
    )
    assert complete is True
    assert payload["dimensions"][0]["overallScore"] == "7.5/10"
    assert payload["dimensions"][1]["overallScore"] == "8.2/10"


def test_partial_coverage_is_flagged_incomplete():
    """Rescore came back for security only: serve it, but flag it uncacheable."""
    deps = scoring.ScoringDeps(
        dismissed_keys=lambda pdir: {("R1", "a.py", 1)},
        deleted_keys=lambda pdir: set(),
        rescore_runs_by_dimension=lambda dims, root, project, dismissed, deleted=None, params=None: {
            "security": {"overallScore": "7.5/10", "overallGrade": "Good"},
        },
        recompute_summary=lambda dims, summary, params=None: summary,
    )
    payload, complete = _rescore_accumulated_with_coverage(
        _acc([_dim("security"), _dim("performance")]), Path("/reports"), "proj", deps=deps,
    )
    assert complete is False
    # The payload is still the best available answer for THIS request.
    assert payload["dimensions"][0]["overallScore"] == "7.5/10"
    assert payload["dimensions"][1]["overallScore"] == "5.0/10"  # raw kept
