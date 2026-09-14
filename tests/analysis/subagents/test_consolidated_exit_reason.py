"""Consolidated mode threads pool.exit_reason into per-dim Evidence."""
from __future__ import annotations

import json
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


class _RecordingSink:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def info(self, msg: str) -> None: ...
    def debug(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...
    def success(self, msg: str) -> None: ...


def test_collect_consolidated_results_logs_when_queue_read_fails(tmp_path):
    """A malformed taken-log entry (missing 'files') must be logged, not dropped silently.

    ``read_state`` validates the queue file's top-level shape but not each
    "taken" entry, so a corrupted entry surfaces as a KeyError from
    ``all_taken_files()`` -- one of the exception types the call site is
    expected to catch and log. The warning goes to the injected ``LogSink``
    (this is an inner layer; no stdlib logger here).
    """
    config = MagicMock()
    config.language = "python"
    config.src = tmp_path
    config.source_file_count = 100
    config.target = None
    config.evaluators_dir = None

    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "consolidated_evidence.jsonl").write_text("", encoding="utf-8")

    # A structurally valid queue file (passes read_state's shape checks) whose
    # "taken" entry is missing "files" -- triggers KeyError in all_taken_files().
    queue_path = evidence_dir / "consolidated_queue.json"
    queue_path.write_text(
        json.dumps({
            "version": 1,
            "pending": [],
            "taken": [{"agent": "a1", "ts": 0.0}],  # missing "files"
        }),
        encoding="utf-8",
    )

    ctx_obj = MagicMock()
    ctx_obj.date_str = "2026-05-23"

    run_ctx = _ConsolidatedRunContext(
        dimensions=["security"], ctx=ctx_obj, results=[], files=[],
    )
    paths = _ConsolidatedPaths(evidence_dir=evidence_dir, compiled_dir=None)

    sink = _RecordingSink()
    with patch(
        "quodeq.analysis.subagents._consolidated.SubagentPool.deduplicate_jsonl"
    ), patch(
        "quodeq.analysis.subagents._consolidated.parse_jsonl_to_evidence_by_dimension",
        return_value={},
    ):
        _collect_consolidated_results(config, run_ctx, paths, log=sink)

    assert any(
        "consolidated queue" in msg.lower() and str(queue_path) in msg
        for msg in sink.warnings
    ), f"expected a warning naming {queue_path}, got: {sink.warnings}"
