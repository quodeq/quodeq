"""The memo gate: a partial accumulated rescore must never enter ``_PAYLOADS``.

End-to-end mutation cover for the ``if complete:`` gate in
``get_project_scores_stamped``. The scenario is the 2026-07-29 production
incident: a winning run whose full read covers only a subset of the
dimensions its rows graded may be SERVED once, but memoizing it makes the
partial payload a hit that survives run completion.

The assertion is on the memo write itself, not on score values: the shared
fixtures bake no findings, so a poisoned and a correct payload can be
score-identical, and the write is the only reliable observable.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from quodeq.services import scoring
from quodeq.services.dashboard import clear_shared_dimension_cache, make_run_dimension_fetcher
from quodeq.services.dismissed import dismiss_finding
from quodeq.services.scoring import get_project_scores
from quodeq.shared.stamp_memo import StampCache
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


class _SpyingMemo(StampCache):
    def __init__(self):
        super().__init__()
        self.puts: list = []

    def put(self, key, stamp, payload):
        self.puts.append(stamp)
        super().put(key, stamp, payload)


@pytest.fixture()
def persist_spy():
    memo = _SpyingMemo()
    with patch("quodeq.services.scoring._project_scores._PAYLOADS", memo):
        yield memo.puts


def test_partial_rescore_is_served_but_not_persisted(project, persist_spy):
    def partial_reads(reports_root, project_name):
        full = make_run_dimension_fetcher(reports_root, project_name)
        # Simulate the incident: only the first-finished dimension came back.
        return lambda run_id: [d for d in full(run_id) if d.dimension == "security"]

    deps = scoring.ScoringDeps(base_fetcher_factory=partial_reads)
    payload = get_project_scores(project, "proj", deps=deps)

    assert payload is not None, "partial coverage must degrade to serving, not erroring"
    assert persist_spy == [], (
        "a rescore that covered 1 of 2 dimensions was persisted to the "
        "payload memo, it will be served forever (the 2026-07-29 bug)"
    )


def test_complete_rescore_is_persisted(project, persist_spy):
    """The discriminating arm: the same flow WITH full coverage does persist."""
    payload = get_project_scores(project, "proj")

    assert payload is not None
    assert len(persist_spy) == 1, (
        "a fully-covered rescore should enter the payload memo "
        "exactly once — if this stopped happening the gate is over-blocking"
    )
