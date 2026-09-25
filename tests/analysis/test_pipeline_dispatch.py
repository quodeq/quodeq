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
from quodeq.shared.constants import CC_PHASE_ANALYZING_START


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
                          "get_provider_type") as m:
        m.load_analysis_context.return_value = (["security"], MagicMock())
        m.run_incremental_loop.return_value = {}
        m.run_per_dimension_loop.return_value = {}
        m.process_consolidated_dimensions.return_value = {}
        m.get_provider_type.return_value = "api"

        from quodeq.analysis._pipeline import _run_dimensions
        _run_dimensions(_make_config(incremental=False))

        assert not m.run_incremental_loop.called, "Clean scan unexpectedly used run_incremental_loop"


def test_diff_from_uses_per_dim_loop(patched_pipeline):
    """diff_from set -> run_per_dimension_loop, never the incremental loop.

    Diff mode is evidence-only -- fingerprint reuse doesn't apply, so
    even with incremental=True (default), the diff path takes precedence.
    Note: the CLI translation layer actually sets incremental=False
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


def _deadline_calls(mock_emit_marker):
    return [
        c for c in mock_emit_marker.call_args_list
        if c.args[:1] == (CC_PHASE_ANALYZING_START,)
    ]


def test_deadline_marker_emitted_once_at_the_root_when_set(patched_pipeline):
    """``set_run_deadline`` (``_pipeline_setup.py``) only returns the ISO
    deadline; ``_run_dimensions`` (the composition root for this seam) is
    the one that calls ``emit_marker`` -- exactly once, with the returned
    timestamp and the run's configured budget."""
    with patched_pipeline(*_COMMON_SEAMS, "set_run_deadline") as m:
        m.load_analysis_context.return_value = (["security"], MagicMock())
        m.run_incremental_loop.return_value = {}
        m.set_run_deadline.return_value = "2026-05-02T10:00:00+00:00"

        from quodeq.analysis._pipeline import _run_dimensions
        config = _make_config(incremental=True)
        config.options.time_limit = 600
        _run_dimensions(config)

        calls = _deadline_calls(m.emit_marker)
        assert len(calls) == 1
        assert calls[0].kwargs == {
            "deadline_at": "2026-05-02T10:00:00+00:00", "budget_s": 600,
        }


def test_no_deadline_marker_when_set_run_deadline_skips(patched_pipeline):
    """dry-run/unlimited-budget/pre-set-deadline: ``set_run_deadline``
    returns None and the root emits nothing -- no noise marker."""
    with patched_pipeline(*_COMMON_SEAMS, "set_run_deadline") as m:
        m.load_analysis_context.return_value = (["security"], MagicMock())
        m.run_incremental_loop.return_value = {}
        m.set_run_deadline.return_value = None

        from quodeq.analysis._pipeline import _run_dimensions
        _run_dimensions(_make_config(incremental=True))

        assert _deadline_calls(m.emit_marker) == []
