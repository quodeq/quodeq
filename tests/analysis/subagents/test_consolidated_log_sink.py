"""Post-PR review I2: the consolidated collector logs through the injected sink.

A prior fix replaced a silent ``except: pass`` around
the queue read with a warning, but wired it to a raw stdlib logger in a module
whose public entry point already carries ``log: LogSink``. ``analysis/`` is one
of the inner layers ARCHITECTURE.md requires to take an injected sink, and the
logging-boundary gate could not see the slip because the file was already
declared for a different, legitimate import. These tests pin the conversion.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from quodeq.analysis.subagents import _consolidated
from quodeq.analysis.subagents._consolidated import (
    _ConsolidatedPaths,
    _ConsolidatedRunContext,
    _collect_consolidated_results,
)


class _RecordingSink:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def info(self, msg: str) -> None: ...
    def debug(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...
    def success(self, msg: str) -> None: ...


def _config(tmp_path):
    config = MagicMock()
    config.language = "python"
    config.src = tmp_path
    config.source_file_count = 1
    config.target = None
    config.evaluators_dir = None
    return config


def test_corrupt_queue_warning_reaches_the_injected_sink(tmp_path):
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "consolidated_evidence.jsonl").write_text("", encoding="utf-8")
    # A queue file that exists but cannot be parsed: the exact failure the
    # fix made visible.
    (evidence_dir / "consolidated_queue.json").write_text("{not json", encoding="utf-8")

    ctx_obj = MagicMock()
    ctx_obj.date_str = "2026-09-14"
    run_ctx = _ConsolidatedRunContext(
        dimensions=["security"], ctx=ctx_obj, results=[], files=[], exit_reason=None,
    )
    paths = _ConsolidatedPaths(evidence_dir=evidence_dir, compiled_dir=None)
    sink = _RecordingSink()

    with patch(
        "quodeq.analysis.subagents._consolidated.SubagentPool.deduplicate_jsonl"
    ), patch(
        "quodeq.analysis.subagents._consolidated.parse_jsonl_to_evidence_by_dimension",
        return_value={},
    ):
        _collect_consolidated_results(_config(tmp_path), run_ctx, paths, log=sink)

    assert len(sink.warnings) == 1, sink.warnings
    assert "consolidated queue" in sink.warnings[0]
    assert str(evidence_dir / "consolidated_queue.json") in sink.warnings[0]


def test_consolidated_module_does_not_bind_a_stdlib_logger():
    # The logging-boundary gate keys on file, not on which import the file was
    # declared for, so this is the only regression net for the raw logger.
    assert not hasattr(_consolidated, "_logger")
    assert not hasattr(_consolidated, "logging")
