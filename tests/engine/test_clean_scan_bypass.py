"""Regression tests for clean-scan (incremental=False) prior-findings bypass.

Before this fix, a clean scan still loaded all prior findings from
<dim>_evidence.jsonl and routed them through inline re-verification,
making prompts larger and re-checking findings the user wanted ignored.

The bypass: when config.options.incremental is False, _prepare_findings_and_queue
skips _load_and_filter_previous entirely so no prior findings reach the queue.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from quodeq.analysis.subagents.runner import _prepare_findings_and_queue


def _make_dc(tmp_path: Path) -> SimpleNamespace:
    """Minimal _DimensionContext-shaped object for the call under test."""
    return SimpleNamespace(
        dim_id="security",
        idx=1,
        ctx=SimpleNamespace(total=1),
        files=["a.py", "b.py"],
        evidence_dir=tmp_path,
    )


def _make_config(*, incremental: bool, src: Path) -> SimpleNamespace:
    """Minimal RunConfig-shaped object exposing the fields _prepare uses."""
    return SimpleNamespace(
        options=SimpleNamespace(incremental=incremental, verify_findings=True),
        src=src,
        standards_dir=None,
        work_dir=src,
    )


def test_clean_scan_skips_loading_prior_findings(tmp_path):
    """incremental=False must NOT call _load_and_filter_previous."""
    config = _make_config(incremental=False, src=tmp_path)
    dc = _make_dc(tmp_path)
    with patch(
        "quodeq.analysis.subagents.runner._load_and_filter_previous"
    ) as mock_load:
        result = _prepare_findings_and_queue(config, dc)
    mock_load.assert_not_called()
    assert result.inline_findings == []
    assert result.mini_verify_findings == []


def test_incremental_scan_still_loads_prior_findings(tmp_path):
    """incremental=True must keep calling _load_and_filter_previous."""
    config = _make_config(incremental=True, src=tmp_path)
    dc = _make_dc(tmp_path)
    with patch(
        "quodeq.analysis.subagents.runner._load_and_filter_previous",
        return_value=[],
    ) as mock_load:
        _prepare_findings_and_queue(config, dc)
    mock_load.assert_called_once_with(config, dc.dim_id, dc.evidence_dir)


def test_fresh_run_no_prior_jsonl_is_safe(tmp_path):
    """incremental=True (default) with no prior evidence JSONL must not crash.

    Regression guard: after Task 1's default flip, _prepare_findings_and_queue
    runs the incremental branch on every default run. When _load_and_filter_previous
    returns [] (no prior file), the if-prev_findings guard must suppress all
    carry-forward/partition logic and still produce an empty result cleanly.
    """
    config = _make_config(incremental=True, src=tmp_path)
    dc = _make_dc(tmp_path)
    # Simulate a first-ever run: no previous findings, no previous fingerprint.
    with patch(
        "quodeq.analysis.subagents.runner._load_and_filter_previous",
        return_value=[],  # no prior JSONL
    ):
        result = _prepare_findings_and_queue(config, dc)

    assert result.inline_findings == []
    assert result.mini_verify_findings == []
