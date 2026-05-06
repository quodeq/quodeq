"""Regression: a single-dim run after a bundle run must reuse the bundle's fingerprint.

Reported 2026-05-06: `quodeq evaluate . --dimensions security` after a nightly
that ran 5 dimensions including security re-analyzed every file from scratch
instead of carrying forward the security_fingerprint.json the nightly wrote.
"""
from quodeq.analysis._types import AnalysisOptions


def test_analysis_options_incremental_defaults_true():
    """The internal incremental strategy flag defaults to True.

    A run that never explicitly opts out should carry-forward by default.
    """
    opts = AnalysisOptions()
    assert opts.incremental is True, (
        "Default-False causes single-dim re-runs to ignore prior bundle fingerprints. "
        "See docs/superpowers/plans/2026-05-06-incremental-by-default.md"
    )
