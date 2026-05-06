"""Pipeline dispatch routing tests for incremental-by-default.

After the AnalysisOptions.incremental default flip, every run reaches
run_incremental_loop unless options.incremental is explicitly False
(which the CLI/API layer sets when the user requests --clean-scan or
when --diff-from is in play).
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

from quodeq.analysis._types import AnalysisOptions, RunConfig


def _make_config(*, incremental: bool = True, diff_from: str | None = None) -> RunConfig:
    """Build a minimal RunConfig for dispatch tests.

    `incremental=True` is the post-default-flip default and represents
    "no clean scan requested". `incremental=False` simulates the user
    requesting --clean-scan.
    """
    opts = AnalysisOptions(incremental=incremental, diff_from=diff_from)
    return RunConfig(src=Path("/tmp/fake-src"), language="python", options=opts)


@patch("quodeq.analysis._pipeline.run_incremental_loop")
@patch("quodeq.analysis._pipeline.run_per_dimension_loop")
@patch("quodeq.analysis._pipeline.process_consolidated_dimensions")
@patch("quodeq.analysis._pipeline.load_analysis_context")
@patch("quodeq.analysis._pipeline._persist_dim_estimates")
@patch("quodeq.analysis._pipeline.emit_marker")
def test_default_run_uses_incremental_loop(
    emit, persist, load_ctx, consolidated, per_dim, incr,
):
    """Default (incremental=True, no diff_from) -> run_incremental_loop."""
    load_ctx.return_value = (["security"], MagicMock())
    incr.return_value = {}
    per_dim.return_value = {}
    consolidated.return_value = {}

    from quodeq.analysis._pipeline import _run_dimensions
    config = _make_config(incremental=True)
    _run_dimensions(config)

    assert incr.called, "Default run did not reach run_incremental_loop"
    assert not per_dim.called
    assert not consolidated.called


@patch("quodeq.analysis._pipeline.run_incremental_loop")
@patch("quodeq.analysis._pipeline.run_per_dimension_loop")
@patch("quodeq.analysis._pipeline.process_consolidated_dimensions")
@patch("quodeq.analysis._pipeline.load_analysis_context")
@patch("quodeq.analysis._pipeline._persist_dim_estimates")
@patch("quodeq.analysis._pipeline.emit_marker")
@patch("quodeq.analysis._pipeline._get_provider_type")
@patch("quodeq.analysis._pipeline.get_ai_cmd")
def test_clean_scan_skips_incremental_loop(
    get_ai, get_prov, emit, persist, load_ctx, consolidated, per_dim, incr,
):
    """Clean scan (incremental=False) skips run_incremental_loop."""
    load_ctx.return_value = (["security"], MagicMock())
    incr.return_value = {}
    per_dim.return_value = {}
    consolidated.return_value = {}
    get_prov.return_value = "api"

    from quodeq.analysis._pipeline import _run_dimensions
    config = _make_config(incremental=False)
    _run_dimensions(config)

    assert not incr.called, "Clean scan unexpectedly used run_incremental_loop"


@patch("quodeq.analysis._pipeline.run_incremental_loop")
@patch("quodeq.analysis._pipeline.run_per_dimension_loop")
@patch("quodeq.analysis._pipeline.load_analysis_context")
@patch("quodeq.analysis._pipeline._persist_dim_estimates")
@patch("quodeq.analysis._pipeline.emit_marker")
def test_diff_from_uses_per_dim_loop(emit, persist, load_ctx, per_dim, incr):
    """diff_from set -> run_per_dimension_loop, never the incremental loop.

    Diff mode is evidence-only -- fingerprint reuse doesn't apply, so
    even with incremental=True (default), the diff path takes precedence.
    Note: the CLI translation layer (Task 3) actually sets incremental=False
    when diff_from is given, but this test verifies the pipeline-level
    branch ordering directly.
    """
    load_ctx.return_value = (["security"], MagicMock())
    incr.return_value = {}
    per_dim.return_value = {}

    from quodeq.analysis._pipeline import _run_dimensions
    config = _make_config(incremental=True, diff_from="origin/main")
    _run_dimensions(config)

    assert per_dim.called, "diff_from did not route to run_per_dimension_loop"
    assert not incr.called, "diff_from unexpectedly used run_incremental_loop"
