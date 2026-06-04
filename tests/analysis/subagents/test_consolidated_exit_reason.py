"""Consolidated mode threads pool.exit_reason into per-dim Evidence."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from quodeq.analysis.subagents._consolidated import (
    _ConsolidatedPaths,
    _ConsolidatedRunContext,
    _collect_consolidated_results,
)


def test_collect_consolidated_results_threads_exit_reason_into_context(tmp_path):
    """The EvidenceContext built for consolidated parsing carries pool.exit_reason."""
    config = MagicMock()
    config.language = "python"
    config.src = tmp_path
    config.source_file_count = 100
    config.target = None
    config.evaluators_dir = None

    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    # Touch the merged JSONL so deduplicate_jsonl is happy with the path.
    (evidence_dir / "consolidated_evidence.jsonl").write_text("", encoding="utf-8")

    ctx_obj = MagicMock()
    ctx_obj.date_str = "2026-05-23"

    run_ctx = _ConsolidatedRunContext(
        dimensions=["security"],
        ctx=ctx_obj,
        results=[],
        files=[],
        exit_reason="time_limit",
    )
    paths = _ConsolidatedPaths(evidence_dir=evidence_dir, compiled_dir=None)

    with patch(
        "quodeq.analysis.subagents._consolidated.SubagentPool.deduplicate_jsonl"
    ), patch(
        "quodeq.analysis.subagents._consolidated.parse_jsonl_to_evidence_by_dimension",
        return_value={},
    ) as mock_parse:
        _collect_consolidated_results(config, run_ctx, paths)

    # The EvidenceContext passed into the parser must carry the exit_reason.
    assert mock_parse.called, "parse_jsonl_to_evidence_by_dimension was not called"
    ev_ctx_arg = mock_parse.call_args.args[1]
    assert ev_ctx_arg.exit_reason == "time_limit"


def test_collect_consolidated_results_exit_reason_defaults_to_none(tmp_path):
    """When no exit_reason is supplied, EvidenceContext.exit_reason stays None."""
    config = MagicMock()
    config.language = "python"
    config.src = tmp_path
    config.source_file_count = 100
    config.target = None
    config.evaluators_dir = None

    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "consolidated_evidence.jsonl").write_text("", encoding="utf-8")

    ctx_obj = MagicMock()
    ctx_obj.date_str = "2026-05-23"

    run_ctx = _ConsolidatedRunContext(
        dimensions=["security"],
        ctx=ctx_obj,
        results=[],
        files=[],
    )
    paths = _ConsolidatedPaths(evidence_dir=evidence_dir, compiled_dir=None)

    with patch(
        "quodeq.analysis.subagents._consolidated.SubagentPool.deduplicate_jsonl"
    ), patch(
        "quodeq.analysis.subagents._consolidated.parse_jsonl_to_evidence_by_dimension",
        return_value={},
    ) as mock_parse:
        _collect_consolidated_results(config, run_ctx, paths)

    ev_ctx_arg = mock_parse.call_args.args[1]
    assert ev_ctx_arg.exit_reason is None
