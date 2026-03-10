"""Tests for analysis module (stream capture + JSONL extraction)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.engine.analysis import AnalysisConfig, _build_ai_cmd
from quodeq.engine.stream_parser import _extract_jsonl_from_text, extract_evidence_from_stream
from quodeq.engine.stream_validation import is_stream_valid


# ---------------------------------------------------------------------------
# Helpers to build stream-json events
# ---------------------------------------------------------------------------

def _assistant_text_event(text: str) -> str:
    return json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": text}]},
    })


def _assistant_read_event(file_path: str) -> str:
    return json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": file_path}}]},
    })


def _result_event(text: str, is_error: bool = False) -> str:
    d = {"type": "result", "result": text}
    if is_error:
        d["is_error"] = True
    return json.dumps(d)


def _item_completed_event(text: str, reads: list[str] | None = None) -> str:
    content = [{"type": "text", "text": text}]
    if reads:
        for fp in reads:
            content.append({"type": "tool_use", "name": "Read", "input": {"file_path": fp}})
    return json.dumps({
        "type": "item.completed",
        "item": {"type": "agent_message", "text": text, "content": content},
    })


def _evidence_line(**overrides) -> str:
    obj = {"p": "ts-001", "t": "violation", "d": "security", "w": "eval usage",
           "file": "app.ts", "line": 10, "severity": "high", "vt": "violation",
           "reason": "eval is dangerous"}
    obj.update(overrides)
    return json.dumps(obj)


# ---------------------------------------------------------------------------
# _extract_jsonl_from_text
# ---------------------------------------------------------------------------

class TestExtractJsonlFromText:
    def test_extracts_evidence_lines(self):
        from io import StringIO
        out = StringIO()
        text = _evidence_line() + "\nsome non-json line\n" + _evidence_line(p="ts-002", t="compliance")
        count, lines = _extract_jsonl_from_text(text, out)
        assert count == 2
        assert lines == 3

    def test_skips_markdown_fences(self):
        from io import StringIO
        out = StringIO()
        text = "```json\n" + _evidence_line() + "\n```"
        count, _ = _extract_jsonl_from_text(text, out)
        assert count == 1  # evidence line extracted, fences skipped

    def test_skips_non_evidence_json(self):
        from io import StringIO
        out = StringIO()
        text = json.dumps({"some": "object"})  # no "p" or "t" field
        count, _ = _extract_jsonl_from_text(text, out)
        assert count == 0

    def test_empty_text(self):
        from io import StringIO
        out = StringIO()
        count, lines = _extract_jsonl_from_text("", out)
        assert count == 0
        assert lines == 0

    def test_ignores_invalid_verdict(self):
        from io import StringIO
        out = StringIO()
        text = json.dumps({"p": "ts-001", "t": "dismissed"})
        count, _ = _extract_jsonl_from_text(text, out)
        assert count == 0


# ---------------------------------------------------------------------------
# extract_evidence_from_stream
# ---------------------------------------------------------------------------

class TestExtractEvidenceFromStream:
    def test_assistant_text_events(self, tmp_path):
        stream = tmp_path / "stream.json"
        jsonl = tmp_path / "evidence.jsonl"
        stream.write_text(
            _assistant_text_event(_evidence_line()) + "\n"
            + _assistant_text_event(_evidence_line(p="ts-002", t="compliance")) + "\n"
        )
        files_read = extract_evidence_from_stream(stream, jsonl)
        lines = jsonl.read_text().strip().splitlines()
        assert len(lines) == 2
        assert files_read == 0

    def test_tracks_files_read(self, tmp_path):
        stream = tmp_path / "stream.json"
        jsonl = tmp_path / "evidence.jsonl"
        stream.write_text(
            _assistant_read_event("/src/app.ts") + "\n"
            + _assistant_read_event("/src/util.ts") + "\n"
            + _assistant_read_event("/src/app.ts") + "\n"  # duplicate
        )
        files_read = extract_evidence_from_stream(stream, jsonl)
        assert files_read == 2  # unique count

    def test_result_events(self, tmp_path):
        stream = tmp_path / "stream.json"
        jsonl = tmp_path / "evidence.jsonl"
        stream.write_text(_result_event(_evidence_line()) + "\n")
        files_read = extract_evidence_from_stream(stream, jsonl)
        lines = jsonl.read_text().strip().splitlines()
        assert len(lines) == 1
        assert files_read == 0

    def test_item_completed_events(self, tmp_path):
        stream = tmp_path / "stream.json"
        jsonl = tmp_path / "evidence.jsonl"
        stream.write_text(
            _item_completed_event(_evidence_line(), reads=["/src/a.ts", "/src/b.ts"]) + "\n"
        )
        files_read = extract_evidence_from_stream(stream, jsonl)
        assert files_read == 2

    def test_empty_stream(self, tmp_path):
        stream = tmp_path / "stream.json"
        jsonl = tmp_path / "evidence.jsonl"
        stream.write_text("")
        files_read = extract_evidence_from_stream(stream, jsonl)
        assert files_read == 0
        assert jsonl.read_text() == ""

    def test_mixed_events(self, tmp_path):
        stream = tmp_path / "stream.json"
        jsonl = tmp_path / "evidence.jsonl"
        stream.write_text("\n".join([
            _assistant_text_event(_evidence_line(p="ts-001")),
            _assistant_read_event("/src/app.ts"),
            _result_event(_evidence_line(p="ts-002", t="compliance")),
            _item_completed_event(_evidence_line(p="ts-003"), reads=["/src/b.ts"]),
            json.dumps({"type": "system", "data": "ignored"}),
        ]) + "\n")
        files_read = extract_evidence_from_stream(stream, jsonl)
        lines = jsonl.read_text().strip().splitlines()
        # item.completed extracts from both item.text and content blocks
        assert len(lines) == 4
        assert files_read == 2

    def test_malformed_json_lines_skipped(self, tmp_path):
        stream = tmp_path / "stream.json"
        jsonl = tmp_path / "evidence.jsonl"
        stream.write_text("not json\n" + _assistant_text_event(_evidence_line()) + "\n")
        files_read = extract_evidence_from_stream(stream, jsonl)
        lines = jsonl.read_text().strip().splitlines()
        assert len(lines) == 1


# ---------------------------------------------------------------------------
# is_stream_valid
# ---------------------------------------------------------------------------

class TestIsStreamValid:
    def test_valid_stream(self, tmp_path):
        stream = tmp_path / "stream.json"
        stream.write_text(
            _assistant_text_event("hello") + "\n"
            + _result_event("done") + "\n"
        )
        assert is_stream_valid(stream) is True

    def test_error_stream(self, tmp_path):
        stream = tmp_path / "stream.json"
        stream.write_text(_result_event("API error", is_error=True) + "\n")
        assert is_stream_valid(stream) is False

    def test_empty_file(self, tmp_path):
        stream = tmp_path / "stream.json"
        stream.write_text("")
        assert is_stream_valid(stream) is False

    def test_missing_file(self, tmp_path):
        stream = tmp_path / "nonexistent.json"
        assert is_stream_valid(stream) is False


# ---------------------------------------------------------------------------
# _build_ai_cmd — prevent regressions in CLI tool/permission flags
# ---------------------------------------------------------------------------

class TestBuildAiCmd:
    """Guard against regressions that silently break evaluations (0 findings)."""

    def test_bash_in_allowed_tools(self):
        """Bash must be in the tools list — analysis prompts rely on it."""
        args, _ = _build_ai_cmd("test prompt", AnalysisConfig())
        tools_idx = args.index("--tools")
        tools_value = args[tools_idx + 1]
        assert "Bash" in tools_value.split(",")

    def test_read_glob_grep_in_allowed_tools(self):
        """File exploration tools must be available."""
        args, _ = _build_ai_cmd("test prompt", AnalysisConfig())
        tools_idx = args.index("--tools")
        tools_value = args[tools_idx + 1]
        for tool in ("Read", "Glob", "Grep"):
            assert tool in tools_value.split(","), f"{tool} missing from --tools"

    def test_bypass_permissions_with_mcp(self, tmp_path):
        """MCP mode must use bypassPermissions — without it, tools are blocked
        in --print mode and the evaluation silently produces 0 findings."""
        jsonl = tmp_path / "findings.jsonl"
        args, mcp_path = _build_ai_cmd(
            "test prompt", AnalysisConfig(jsonl_file=jsonl),
        )
        assert "--permission-mode" in args, (
            "--permission-mode flag is missing; without bypassPermissions "
            "the AI cannot use tools in --print mode"
        )
        perm_idx = args.index("--permission-mode")
        assert args[perm_idx + 1] == "bypassPermissions"

    def test_mcp_config_created_with_jsonl(self, tmp_path):
        """When jsonl_file is set, MCP config must be generated."""
        jsonl = tmp_path / "findings.jsonl"
        args, mcp_path = _build_ai_cmd(
            "test prompt", AnalysisConfig(jsonl_file=jsonl),
        )
        assert mcp_path is not None
        assert "--mcp-config" in args
        assert "mcp__findings__report_finding" in args

    def test_print_mode_always_set(self):
        """Analysis must run in --print (non-interactive) mode."""
        args, _ = _build_ai_cmd("test prompt", AnalysisConfig())
        assert "--print" in args
        assert "--output-format" in args
        fmt_idx = args.index("--output-format")
        assert args[fmt_idx + 1] == "stream-json"
