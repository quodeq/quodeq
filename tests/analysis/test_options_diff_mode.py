"""Tests for diff-mode fields on AnalysisOptions."""
from __future__ import annotations

from quodeq.analysis._types import AnalysisOptions


def test_diff_from_defaults_to_none() -> None:
    opts = AnalysisOptions()
    assert opts.diff_from is None


def test_skip_scoring_defaults_to_false() -> None:
    opts = AnalysisOptions()
    assert opts.skip_scoring is False


def test_diff_from_is_storable() -> None:
    opts = AnalysisOptions(diff_from="origin/develop")
    assert opts.diff_from == "origin/develop"


def test_skip_scoring_is_storable() -> None:
    opts = AnalysisOptions(skip_scoring=True)
    assert opts.skip_scoring is True
