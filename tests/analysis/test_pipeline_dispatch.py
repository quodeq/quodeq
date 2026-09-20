"""Pipeline dispatch routing tests for incremental-by-default.

After the AnalysisOptions.incremental default flip, every run reaches
run_incremental_loop unless options.incremental is explicitly False
(which the CLI/API layer sets when the user requests --clean-scan or
when --diff-from is in play).
"""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import DEFAULT, MagicMock, patch

import pytest

from quodeq.analysis.run_types import AnalysisOptions, RunConfig


def _make_config(*, incremental: bool = True, diff_from: str | None = None) -> RunConfig:
    """Build a minimal RunConfig for dispatch tests.

    `incremental=True` is the post-default-flip default and represents
    "no clean scan requested". `incremental=False` simulates the user
    requesting --clean-scan.
    """
    opts = AnalysisOptions(incremental=incremental, diff_from=diff_from)
    return RunConfig(src=Path("/tmp/fake-src"), language="python", options=opts)


@pytest.fixture
def patched_pipeline():
    """Patch the named ``_pipeline`` attributes, yielding the mocks as a namespace.

    Each test names exactly the seams it needs: what a test leaves unpatched
    is what it means to exercise for real.
    """
    @contextmanager
    def _patch(*names: str):
        with patch.multiple("quodeq.analysis._pipeline",
                            **{name: DEFAULT for name in names}) as mocks:
            yield SimpleNamespace(**mocks)

    return _patch


_COMMON_SEAMS = ("run_incremental_loop", "run_per_dimension_loop",
                 "load_analysis_context", "_persist_dim_estimates", "emit_marker")


def test_default_run_uses_incremental_loop(patched_pipeline):
    """Default (incremental=True, no diff_from) -> run_incremental_loop."""
    with patched_pipeline(*_COMMON_SEAMS, "process_consolidated_dimensions") as m:
        m.load_analysis_context.return_value = (["security"], MagicMock())
        m.run_incremental_loop.return_value = {}
        m.run_per_dimension_loop.return_value = {}
        m.process_consolidated_dimensions.return_value = {}

        from quodeq.analysis._pipeline import _run_dimensions
        _run_dimensions(_make_config(incremental=True))

        assert m.run_incremental_loop.called, "Default run did not reach run_incremental_loop"
        assert not m.run_per_dimension_loop.called
        assert not m.process_consolidated_dimensions.called


def test_clean_scan_skips_incremental_loop(patched_pipeline):
    """Clean scan (incremental=False) skips run_incremental_loop."""
    with patched_pipeline(*_COMMON_SEAMS, "process_consolidated_dimensions",
                          "_get_provider_type") as m:
        m.load_analysis_context.return_value = (["security"], MagicMock())
        m.run_incremental_loop.return_value = {}
        m.run_per_dimension_loop.return_value = {}
        m.process_consolidated_dimensions.return_value = {}
        m._get_provider_type.return_value = "api"

        from quodeq.analysis._pipeline import _run_dimensions
        _run_dimensions(_make_config(incremental=False))

        assert not m.run_incremental_loop.called, "Clean scan unexpectedly used run_incremental_loop"


def test_diff_from_uses_per_dim_loop(patched_pipeline):
    """diff_from set -> run_per_dimension_loop, never the incremental loop.

    Diff mode is evidence-only -- fingerprint reuse doesn't apply, so
    even with incremental=True (default), the diff path takes precedence.
    Note: the CLI translation layer (Task 3) actually sets incremental=False
    when diff_from is given, but this test verifies the pipeline-level
    branch ordering directly.
    """
    with patched_pipeline(*_COMMON_SEAMS) as m:
        m.load_analysis_context.return_value = (["security"], MagicMock())
        m.run_incremental_loop.return_value = {}
        m.run_per_dimension_loop.return_value = {}

        from quodeq.analysis._pipeline import _run_dimensions
        _run_dimensions(_make_config(incremental=True, diff_from="origin/main"))

        assert m.run_per_dimension_loop.called, "diff_from did not route to run_per_dimension_loop"
        assert not m.run_incremental_loop.called, "diff_from unexpectedly used run_incremental_loop"
