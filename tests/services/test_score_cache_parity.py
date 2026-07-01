"""Differential: trend through the score cache == direct rescoring, with dismissals."""
from pathlib import Path

import pytest

from quodeq.services.dashboard import clear_shared_dimension_cache
from quodeq.services.dismissed import dismiss_finding, dismissed_keys
from quodeq.services.scoring import get_project_scores
from tests.services._scalar_fixtures import build_projected_run


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    clear_shared_dimension_cache()
    yield
    clear_shared_dimension_cache()


def _dismiss(project_dir: Path, req: str, file: str, line: int) -> None:
    """Record a dismissal so dismissed_keys(project_dir) is non-empty (heavy path).

    Uses dismiss_finding() from quodeq.services.dismissed, which appends a
    FindingDismissedEvent to project_dir/actions.jsonl.  The finding dict only
    needs req/file/line; the rest are optional metadata fields.
    """
    dismiss_finding(project_dir, {"req": req, "file": file, "line": line})


def test_dismiss_activates_heavy_path(tmp_path):
    """Sanity check: _dismiss makes dismissed_keys non-empty."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    assert dismissed_keys(project_dir) == set()
    _dismiss(project_dir, "R1", "a.py", 1)
    assert dismissed_keys(project_dir) == {("R1", "a.py", 1)}


def test_trend_identical_cached_vs_direct(tmp_path, monkeypatch):
    reports = tmp_path / "evaluations"
    build_projected_run(reports, "proj", "20260101T000000", {"security": (7.0, "Fair")})
    build_projected_run(reports, "proj", "20260102T000000", {"security": (8.0, "Good")})
    _dismiss(reports / "proj", "R1", "a.py", 1)  # activate the heavy (rescoring) path

    # Verify the heavy path is actually taken (dismissed_keys must be non-empty).
    assert dismissed_keys(reports / "proj"), (
        "_dismiss did not produce a non-empty dismissed_keys; heavy path not exercised"
    )

    cold = get_project_scores(reports, "proj")   # cold cache: misses -> compute + populate
    warm = get_project_scores(reports, "proj")   # warm cache: hits

    monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
    # cache off (kill switch -> make_cache_backed_fetcher returns base unchanged): direct rescoring
    direct = get_project_scores(reports, "proj")

    assert cold["trend"] == direct["trend"]
    assert warm["trend"] == direct["trend"]
    assert len(cold["trend"]) == 2
