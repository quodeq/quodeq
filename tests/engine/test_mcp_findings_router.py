"""Tests for FindingsRouter and get_next_files (split from test_mcp_findings)."""
from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis.mcp.args import parse_args
from quodeq.engine import mcp_findings
from quodeq.analysis.mcp.findings_server import CompiledContext

from tests.engine.conftest import _make_request, _run_server


def _run_server_with_queue(
    input_lines: list[str], findings_file: str,
    queue_path: str, agent_id: str = "test-agent",
) -> list[dict]:
    """Run the MCP server with --queue and --agent-id flags."""
    stdin_text = "\n".join(input_lines) + "\n"
    stdout_buf = StringIO()
    argv = [
        "mcp_findings.py", findings_file,
        "--queue", queue_path,
        "--agent-id", agent_id,
    ]
    with patch.object(sys, "stdin", StringIO(stdin_text)), \
         patch.object(sys, "stdout", stdout_buf), \
         patch.object(sys, "argv", argv):
        mcp_findings.main()
    output = stdout_buf.getvalue().strip()
    return [json.loads(line) for line in output.splitlines() if line.strip()]


class TestFindingsRouter:
    def test_enriches_req_refs_from_compiled(self, tmp_path: Path) -> None:
        findings_file = tmp_path / "findings.jsonl"
        compiled_refs = {
            "S-CON-1": [{"label": "CWE-798", "url": "https://cwe.mitre.org/data/definitions/798.html"}],
        }
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh, CompiledContext(compiled_refs=compiled_refs))
            msg, dup = router.receive({"p": "Confidentiality", "t": "violation", "d": "security", "w": "Hardcoded key", "req": "S-CON-1"})
        assert not dup
        assert "Finding #1" in msg
        written = json.loads(findings_file.read_text().strip())
        assert written["req_refs"] == [{"label": "CWE-798", "url": "https://cwe.mitre.org/data/definitions/798.html"}]

    def test_no_enrichment_without_matching_req(self, tmp_path: Path) -> None:
        findings_file = tmp_path / "findings.jsonl"
        compiled_refs = {"S-CON-1": [{"label": "CWE-798", "url": "https://example.com"}]}
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh, CompiledContext(compiled_refs=compiled_refs))
            router.receive({"p": "P1", "t": "violation", "d": "perf", "w": "Slow", "req": "UNKNOWN-1"})
        written = json.loads(findings_file.read_text().strip())
        assert "req_refs" not in written

    def test_no_enrichment_without_compiled_refs(self, tmp_path: Path) -> None:
        findings_file = tmp_path / "findings.jsonl"
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh)
            router.receive({"p": "P1", "t": "violation", "d": "perf", "w": "Slow", "req": "S-CON-1"})
        written = json.loads(findings_file.read_text().strip())
        assert "req_refs" not in written


class TestGetNextFiles:
    def test_tools_list_includes_get_next_files(self, tmp_path: Path) -> None:
        from quodeq.engine.file_queue import FileQueue
        qp = tmp_path / "queue.json"
        FileQueue(qp, ["a.py", "b.py"])
        responses = _run_server_with_queue(
            [_make_request("tools/list", 1)],
            str(tmp_path / "findings.jsonl"),
            str(qp),
        )
        tools = responses[0]["result"]["tools"]
        names = [t["name"] for t in tools]
        assert "report_finding" in names
        assert "get_next_files" in names

    def test_tools_list_without_queue_has_no_get_next_files(self, tmp_path: Path) -> None:
        responses = _run_server(
            [_make_request("tools/list", 1)],
            str(tmp_path / "findings.jsonl"),
        )
        tools = responses[0]["result"]["tools"]
        names = [t["name"] for t in tools]
        assert "report_finding" in names
        assert "get_next_files" not in names

    def test_get_next_files_returns_batch(self, tmp_path: Path) -> None:
        from quodeq.engine.file_queue import FileQueue
        files = ["src/a.py", "src/b.py", "src/c.py"]
        qp = tmp_path / "queue.json"
        FileQueue(qp, files)
        responses = _run_server_with_queue(
            [_make_request("tools/call", 1, {"name": "get_next_files", "arguments": {"count": 2}})],
            str(tmp_path / "findings.jsonl"),
            str(qp),
        )
        text = responses[0]["result"]["content"][0]["text"]
        assert "2 files" in text
        assert "src/a.py" in text
        assert "src/b.py" in text

    def test_get_next_files_drains_queue(self, tmp_path: Path) -> None:
        from quodeq.engine.file_queue import FileQueue
        qp = tmp_path / "queue.json"
        FileQueue(qp, ["a.py", "b.py"])
        responses = _run_server_with_queue(
            [
                _make_request("tools/call", 1, {"name": "get_next_files", "arguments": {"count": 10}}),
                _make_request("tools/call", 2, {"name": "get_next_files", "arguments": {}}),
            ],
            str(tmp_path / "findings.jsonl"),
            str(qp),
        )
        assert "2 files" in responses[0]["result"]["content"][0]["text"]
        assert "done" in responses[1]["result"]["content"][0]["text"].lower()

    def test_get_next_files_records_agent_id(self, tmp_path: Path) -> None:
        from quodeq.engine.file_queue import FileQueue
        qp = tmp_path / "queue.json"
        FileQueue(qp, ["a.py"])
        _run_server_with_queue(
            [_make_request("tools/call", 1, {"name": "get_next_files", "arguments": {}})],
            str(tmp_path / "findings.jsonl"),
            str(qp),
            agent_id="agent-42",
        )
        q = FileQueue(qp)
        log = q.taken_log()
        assert len(log) == 1
        assert log[0]["agent"] == "agent-42"

    def test_get_next_files_without_queue_returns_error(self, tmp_path: Path) -> None:
        responses = _run_server(
            [_make_request("tools/call", 1, {"name": "get_next_files", "arguments": {}})],
            str(tmp_path / "findings.jsonl"),
        )
        result = responses[0]["result"]
        assert result["isError"] is True
        assert "No file queue" in result["content"][0]["text"]


class TestFindingsRouterMultiDimension:
    def test_derives_dimension_from_req_id(self):
        """In consolidated mode, dimension comes from req_to_dim mapping."""
        import io
        from quodeq.analysis.mcp.findings_server import FindingsRouter

        fh = io.StringIO()
        req_to_dim = {"S-CON-1": "security", "M-MOD-1": "maintainability"}
        reqs = {
            "S-CON-1": {"principle": "Confidentiality", "text": "..."},
            "M-MOD-1": {"principle": "Modularity", "text": "..."},
        }
        router = FindingsRouter(
            output_fh=fh,
            context=CompiledContext(compiled_reqs=reqs, req_to_dim=req_to_dim),
        )

        msg1, dup1 = router.receive({"req": "S-CON-1", "t": "violation", "file": "a.py", "line": 1, "w": "test"})
        msg2, dup2 = router.receive({"req": "M-MOD-1", "t": "violation", "file": "b.py", "line": 2, "w": "test2"})

        import json
        lines = [json.loads(l) for l in fh.getvalue().strip().split("\n")]
        assert lines[0]["d"] == "security"
        assert lines[1]["d"] == "maintainability"

    def test_fallback_to_single_dimension(self):
        """When req_to_dim is empty, falls back to self._dimension."""
        import io
        from quodeq.analysis.mcp.findings_server import FindingsRouter

        fh = io.StringIO()
        reqs = {"S-CON-1": {"principle": "Confidentiality", "text": "..."}}
        router = FindingsRouter(
            output_fh=fh,
            context=CompiledContext(compiled_reqs=reqs, dimension="security"),
        )

        router.receive({"req": "S-CON-1", "t": "violation", "file": "a.py", "line": 1, "w": "test"})

        import json
        line = json.loads(fh.getvalue().strip())
        assert line["d"] == "security"


class TestParseArgs:
    def test_work_dir_flag(self) -> None:
        sa = parse_args(["findings.jsonl", "--work-dir", "/tmp/repo"])
        assert sa.work_dir == "/tmp/repo"

    def test_work_dir_default_none(self) -> None:
        sa = parse_args(["findings.jsonl"])
        assert sa.work_dir is None


class TestSnippetEnrichment:
    def test_enriches_snippet_and_context_from_file(self, tmp_path: Path) -> None:
        src_file = tmp_path / "src" / "example.py"
        src_file.parent.mkdir(parents=True)
        src_file.write_text(
            "import os\n"
            "import sys\n"
            "\n"
            "def hello():\n"
            "    print('hello')\n"
            "\n"
            "def world():\n"
            "    print('world')\n"
            "\n"
            "def main():\n"
            "    hello()\n"
            "    world()\n"
        )
        findings_file = tmp_path / "findings.jsonl"
        ctx = CompiledContext(work_dir=tmp_path)
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh, context=ctx)
            router.receive({
                "p": "Testability", "t": "violation", "d": "test",
                "file": "src/example.py", "line": 4, "end_line": 5,
                "w": "No tests", "reason": "Missing tests",
                "severity": "major", "req": "T-1",
            })
        written = json.loads(findings_file.read_text().strip())
        assert written["snippet"] == "def hello():\n    print('hello')"
        assert ">>> def hello():" in written["context"]
        assert ">>>     print('hello')" in written["context"]
        assert "import sys" in written["context"]

    def test_enriches_single_line_when_no_end_line(self, tmp_path: Path) -> None:
        src_file = tmp_path / "src" / "example.py"
        src_file.parent.mkdir(parents=True)
        src_file.write_text("line1\nline2\nline3\nline4\nline5\n")
        findings_file = tmp_path / "findings.jsonl"
        ctx = CompiledContext(work_dir=tmp_path)
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh, context=ctx)
            router.receive({
                "p": "P1", "t": "violation", "d": "d1",
                "file": "src/example.py", "line": 3,
                "w": "Issue", "reason": "Because", "severity": "minor", "req": "R-1",
            })
        written = json.loads(findings_file.read_text().strip())
        assert written["snippet"] == "line3"
        assert ">>> line3" in written["context"]

    def test_scope_finding_shows_first_lines(self, tmp_path: Path) -> None:
        src_file = tmp_path / "src" / "big.py"
        src_file.parent.mkdir(parents=True)
        lines = [f"line{i}" for i in range(1, 21)]
        src_file.write_text("\n".join(lines) + "\n")
        findings_file = tmp_path / "findings.jsonl"
        ctx = CompiledContext(work_dir=tmp_path)
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh, context=ctx)
            router.receive({
                "p": "P1", "t": "violation", "d": "d1",
                "file": "src/big.py", "line": 1, "scope": "file",
                "w": "Whole file issue", "reason": "Because", "severity": "major", "req": "R-1",
            })
        written = json.loads(findings_file.read_text().strip())
        assert written["scope"] == "file"
        # Snippet contains the full file content
        assert "line1" in written["snippet"]
        assert "line20" in written["snippet"]
        # Context is null for scope findings
        assert written.get("context") is None

    def test_file_not_found_graceful(self, tmp_path: Path) -> None:
        findings_file = tmp_path / "findings.jsonl"
        ctx = CompiledContext(work_dir=tmp_path)
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh, context=ctx)
            router.receive({
                "p": "P1", "t": "violation", "d": "d1",
                "file": "nonexistent.py", "line": 5,
                "w": "Issue", "reason": "Because", "severity": "minor", "req": "R-1",
            })
        written = json.loads(findings_file.read_text().strip())
        assert written.get("snippet", "") == ""
        assert written.get("context", "") == ""

    def test_line_zero_infers_file_scope(self, tmp_path: Path) -> None:
        src_file = tmp_path / "src" / "mod.py"
        src_file.parent.mkdir(parents=True)
        src_file.write_text("import os\nclass Foo:\n    pass\n")
        findings_file = tmp_path / "findings.jsonl"
        ctx = CompiledContext(work_dir=tmp_path)
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh, context=ctx)
            router.receive({
                "p": "P1", "t": "violation", "d": "d1",
                "file": "src/mod.py", "line": 0,
                "w": "Whole file", "reason": "Because", "severity": "minor", "req": "R-1",
            })
        written = json.loads(findings_file.read_text().strip())
        assert written.get("scope") == "file"
        assert "import os" in written.get("snippet", "")
        assert written.get("context") is None


class TestEnrichmentIntegration:
    def test_full_pipeline_enriches_and_preserves_scope(self, tmp_path: Path) -> None:
        """End-to-end: router enriches finding, JSONL is parseable by evidence parser."""
        src_file = tmp_path / "src" / "app.py"
        src_file.parent.mkdir(parents=True)
        src_file.write_text(
            "from flask import Flask\n"
            "\n"
            "app = Flask(__name__)\n"
            "\n"
            "@app.route('/')\n"
            "def index():\n"
            "    return 'hello'\n"
        )
        findings_file = tmp_path / "findings.jsonl"
        ctx = CompiledContext(work_dir=tmp_path)

        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh, context=ctx)
            # Normal finding
            router.receive({
                "p": "Testability", "t": "violation", "d": "test",
                "file": "src/app.py", "line": 6, "end_line": 7,
                "w": "No tests", "reason": "Missing", "severity": "major", "req": "T-1",
            })
            # Scope finding
            router.receive({
                "p": "Structure", "t": "violation", "d": "test",
                "file": "src/app.py", "line": 1, "scope": "file",
                "w": "Wrong layer", "reason": "Because", "severity": "major", "req": "T-2",
            })

        lines = findings_file.read_text().strip().splitlines()
        normal = json.loads(lines[0])
        scoped = json.loads(lines[1])

        # Normal: snippet + context with >>>
        assert "def index():" in normal["snippet"]
        assert ">>> def index():" in normal["context"]

        # Scoped: snippet contains full file, context is null, scope preserved
        assert scoped["scope"] == "file"
        assert "from flask import Flask" in scoped["snippet"]
        assert "return 'hello'" in scoped["snippet"]
        assert scoped.get("context") is None
