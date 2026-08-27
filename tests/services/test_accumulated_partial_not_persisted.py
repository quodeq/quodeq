"""The persist gate: a partial accumulated rescore must never enter the cache.

End-to-end mutation cover for the ``cacheable=lambda: rescore_complete[0]``
gate in ``get_project_scores`` (added with PR #924's guards but previously
untested — neutralizing it left the whole suite green). The scenario is the
2026-07-29 production incident: a rescore that covers only a subset of a
run's dimensions may be SERVED once, but persisting it makes the partial
payload a permanent cache hit that survives run completion.

The assertion is on the persist call itself (``write_cached_accumulated``),
not on score values: the shared fixtures bake no findings, so a poisoned and
a correct payload can be score-identical — the write is the only reliable
observable.
"""
from __future__ import annotations

import pytest

from quodeq.services import _score_cache_fetch, scoring
from quodeq.services.dashboard import clear_shared_dimension_cache
from quodeq.services.dismissed import dismiss_finding
from quodeq.services.scoring import get_project_scores
from tests.services._scalar_fixtures import build_projected_run


@pytest.fixture(autouse=True)
def _fresh_lru():
    clear_shared_dimension_cache()
    yield
    clear_shared_dimension_cache()


@pytest.fixture()
def project(tmp_path):
    reports = tmp_path / "evaluations"
    build_projected_run(
        reports, "proj", "20260101T000000",
        {"security": (7.0, "Fair"), "performance": (6.0, "Adequate")},
    )
    # An active dismissal engages the rescore path (complete=True otherwise).
    dismiss_finding(reports / "proj", {"req": "R1", "file": "a.py", "line": 1})
    return reports


@pytest.fixture()
def persist_spy(monkeypatch):
    calls: list = []
    real_write = _score_cache_fetch.write_cached_accumulated

    def spying_write(conn, project_name, version, payload):
        calls.append(version)
        return real_write(conn, project_name, version, payload)

    # Patch where cached_accumulated resolves the write, not the facade:
    # score_cache only re-exports the name.
    monkeypatch.setattr(_score_cache_fetch, "write_cached_accumulated", spying_write)
    return calls


def test_partial_rescore_is_served_but_not_persisted(project, persist_spy):
    real = scoring._rescore_runs_by_dimension

    def partial(dims, reports_root, project_name, dismissed, deleted=None, *, params=None):
        full = real(dims, reports_root, project_name, dismissed, deleted, params=params)
        # Simulate the incident: only the first-finished dimension came back.
        return {k: v for k, v in full.items() if k == "security"}

    deps = scoring.ScoringDeps(rescore_runs_by_dimension=partial)
    payload = get_project_scores(project, "proj", deps=deps)

    assert payload is not None, "partial coverage must degrade to serving, not erroring"
    assert persist_spy == [], (
        "a rescore that covered 1 of 2 dimensions was persisted to the "
        "accumulated cache — it will be served forever (the 2026-07-29 bug)"
    )


def test_complete_rescore_is_persisted(project, persist_spy):
    """The discriminating arm: the same flow WITH full coverage does persist."""
    payload = get_project_scores(project, "proj")

    assert payload is not None
    assert len(persist_spy) == 1, (
        "a fully-covered rescore should be written to the accumulated cache "
        "exactly once — if this stopped happening the gate is over-blocking"
    )
