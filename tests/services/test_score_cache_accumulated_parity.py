"""Differential + correctness for the rows-backed accumulated payload: identical
to direct, run-set invalidation, and parent projects never memoized."""

import pytest

from quodeq.services.dashboard import clear_shared_dimension_cache
from quodeq.services.dismissed import dismiss_finding
from quodeq.services.scoring import get_project_scores, get_project_scores_stamped
from tests.services._scalar_fixtures import build_projected_run


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    clear_shared_dimension_cache()
    yield
    clear_shared_dimension_cache()


def test_accumulated_identical_cached_vs_direct(tmp_path, monkeypatch):
    reports = tmp_path / "evaluations"
    build_projected_run(reports, "proj", "20260101T000000", {"security": (7.0, "Fair")})
    dismiss_finding(reports / "proj", {"req": "R1", "file": "a.py", "line": 1})

    cold = get_project_scores(reports, "proj")   # miss -> compute + cache
    warm = get_project_scores(reports, "proj")   # hit

    monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
    direct = get_project_scores(reports, "proj")

    assert cold["accumulated"] == direct["accumulated"]
    assert warm["accumulated"] == direct["accumulated"]


def test_new_run_invalidates_accumulated(tmp_path, monkeypatch):
    reports = tmp_path / "evaluations"
    build_projected_run(reports, "proj", "20260101T000000", {"security": (7.0, "Fair")})
    dismiss_finding(reports / "proj", {"req": "R1", "file": "a.py", "line": 1})
    get_project_scores(reports, "proj")                    # cache under version A
    build_projected_run(reports, "proj", "20260102T000000", {"security": (9.0, "Good")})
    second = get_project_scores(reports, "proj")           # run-set changed -> version B
    assert len(second["availableRuns"]) == 2               # not the stale 1-run payload
    monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
    assert second["accumulated"] == get_project_scores(reports, "proj")["accumulated"]


def test_parent_project_is_not_memoized(tmp_path):
    """A project WITH children folds in child dismissals the stamp cannot see,
    so its payload is built on every request (stamp None) and never memoized."""
    reports = tmp_path / "evaluations"
    build_projected_run(reports, "parent", "20260101T000000", {"security": (7.0, "Fair")})
    child = reports / "child"
    child.mkdir(parents=True)
    (child / "repository_info.json").write_text('{"parent": "parent"}', encoding="utf-8")

    first, stamp = get_project_scores_stamped(reports, "parent")
    second, _ = get_project_scores_stamped(reports, "parent")
    assert stamp is None and first is not None and first is not second
