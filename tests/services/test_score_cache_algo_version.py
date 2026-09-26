"""Every persistent score cache version folds in the grade algo version.

The trend scalar cache already keyed on ``GRADE_ALGO_VERSION``; the run-scoped,
suppression-state and accumulated versions keyed only on the writer epoch,
params and suppressions. A scoring-formula bump therefore re-derived run
detail and trend while project cards and the accumulated Overview kept
serving the previous algorithm's numbers until the next dismiss or params
edit. Reading the version at call time makes later bumps self-invalidating.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.core.scoring import projector_scoring
from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services.score_cache import (
    accumulated_cache_version,
    run_scoped_version,
    score_cache_version,
)

_OTHER_ALGO_VERSION = 999


def _bump(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(projector_scoring, "GRADE_ALGO_VERSION", _OTHER_ALGO_VERSION)


def test_run_scoped_version_changes_with_algo_version(monkeypatch: pytest.MonkeyPatch) -> None:
    before = run_scoped_version(DEFAULT_PARAMS, set(), set(), set(), set())
    _bump(monkeypatch)
    assert run_scoped_version(DEFAULT_PARAMS, set(), set(), set(), set()) != before


def test_accumulated_version_changes_with_algo_version(monkeypatch: pytest.MonkeyPatch) -> None:
    before = accumulated_cache_version(DEFAULT_PARAMS, [], None)
    _bump(monkeypatch)
    assert accumulated_cache_version(DEFAULT_PARAMS, [], None) != before


def test_score_cache_version_changes_with_algo_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = score_cache_version(tmp_path, DEFAULT_PARAMS)
    _bump(monkeypatch)
    assert score_cache_version(tmp_path, DEFAULT_PARAMS) != before
