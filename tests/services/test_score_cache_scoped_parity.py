"""Parity gate: cached (cold + warm) == kill-switch direct across suppression scenarios.

This is the safety contract for the per-run scoped score-cache refactor. Because
``build_projected_run`` bakes the SQL grades directly (a dismiss only flips a
verdict; the numbers do not move), the full ``get_project_scores`` payload must
be byte-identical between the cache-on path (cold compute+populate, then warm
hits) and the cache-off (kill-switch) direct path for every scenario below.

Every later task in the refactor must keep this test green. If it goes red, the
refactor changed scoring output -- stop and fix before proceeding.
"""
import json

import pytest

from quodeq.services.dashboard import clear_shared_dimension_cache
from quodeq.services.deleted import delete_finding
from quodeq.services.dismissed import dismiss_finding
from quodeq.services.scoring import get_project_scores
from tests.services._scalar_fixtures import build_projected_run


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    clear_shared_dimension_cache()
    yield
    clear_shared_dimension_cache()


def _two_runs(reports):
    build_projected_run(reports, "proj", "20260101T000000", {"security": (7.0, "Fair")})
    build_projected_run(reports, "proj", "20260102T000000", {"security": (8.0, "Good")})


def _cached_equals_direct(reports, monkeypatch):
    """Cold (compute+populate) and warm (hits) must equal the kill-switch direct path."""
    monkeypatch.delenv("QUODEQ_DISABLE_SCORE_CACHE", raising=False)
    clear_shared_dimension_cache()
    cold = get_project_scores(reports, "proj")
    warm = get_project_scores(reports, "proj")
    monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
    clear_shared_dimension_cache()
    direct = get_project_scores(reports, "proj")
    monkeypatch.delenv("QUODEQ_DISABLE_SCORE_CACHE", raising=False)
    assert json.dumps(cold, sort_keys=True) == json.dumps(direct, sort_keys=True)
    assert json.dumps(warm, sort_keys=True) == json.dumps(direct, sort_keys=True)


def test_parity_no_suppression(tmp_path, monkeypatch):
    reports = tmp_path / "evaluations"
    _two_runs(reports)
    _cached_equals_direct(reports, monkeypatch)


def test_parity_with_dismissal(tmp_path, monkeypatch):
    reports = tmp_path / "evaluations"
    _two_runs(reports)
    dismiss_finding(reports / "proj", {"req": "R1", "file": "a.py", "line": 1})
    _cached_equals_direct(reports, monkeypatch)


def test_parity_with_deletion(tmp_path, monkeypatch):
    reports = tmp_path / "evaluations"
    _two_runs(reports)
    delete_finding(
        reports / "proj",
        {"dimension": "security", "principle": "P1", "file": "a.py"},
    )
    _cached_equals_direct(reports, monkeypatch)


def test_parity_with_mixed_suppression(tmp_path, monkeypatch):
    reports = tmp_path / "evaluations"
    _two_runs(reports)
    dismiss_finding(reports / "proj", {"req": "R1", "file": "a.py", "line": 1})
    delete_finding(
        reports / "proj",
        {"dimension": "security", "principle": "P2", "file": "b.py"},
    )
    _cached_equals_direct(reports, monkeypatch)
