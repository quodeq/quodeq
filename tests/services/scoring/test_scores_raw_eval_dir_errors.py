"""_prefer_eval_rescore's eval-dir listing must still raise OSError.

count_eval_files (data/fs/run_files.py) swallows OSError from an existing-
but-unlistable evaluation/ dir by default (a permissions problem, a race)
to keep it "just a read", returning None instead. _scores_raw's own inline
``eval_dir.iterdir()`` used to let that OSError propagate instead, and
get_scores_raw's callers rely on that to surface a real filesystem problem
rather than silently falling back to the eval-JSON path. The switch to the
run_files helper must keep that by passing strict=True.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.services.scoring import ScoringDeps, get_scores_raw


def test_get_scores_raw_propagates_oserror_from_unreadable_eval_dir(tmp_path, monkeypatch):
    reports_root = tmp_path / "reports"
    run_dir = reports_root / "proj" / "run-1"
    (run_dir / "evaluation").mkdir(parents=True)

    def explode(self):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "iterdir", explode)

    # has_project_wide_filters must be True so _prefer_eval_rescore reaches
    # the eval-dir listing at all.
    deps = ScoringDeps(dismissed_keys=lambda pd: {("R1", "a.py", 1)}, deleted_keys=lambda pd: set())

    with pytest.raises(OSError):
        get_scores_raw(reports_root, "proj", "run-1", deps=deps)


def test_get_scores_raw_treats_missing_eval_dir_as_no_eval_files(tmp_path, monkeypatch):
    """Control case: no evaluation/ dir at all is still "no signal", not an
    error -- only a listing failure on an EXISTING dir must raise."""
    reports_root = tmp_path / "reports"
    run_dir = reports_root / "proj" / "run-1"
    run_dir.mkdir(parents=True)

    deps = ScoringDeps(dismissed_keys=lambda pd: {("R1", "a.py", 1)}, deleted_keys=lambda pd: set())

    # No events.jsonl and no evaluation dir: falls through to the eval-files
    # builder, which returns the empty-response shape rather than raising.
    result = get_scores_raw(reports_root, "proj", "run-1", deps=deps)
    assert result["dimensions"] == []
