"""Tests for snippet/context enrichment in FindingsRouter (split from test_mcp_findings_router)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.engine import mcp_findings
from quodeq.analysis.mcp.findings_server import CompiledContext


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


class TestInjectableFileReader:
    """Verify that FindingsRouter can use an injected file_reader instead of the filesystem."""

    def test_enriches_via_injected_reader(self, tmp_path: Path) -> None:
        file_contents = {"src/example.py": "line1\nline2\nline3\nline4\nline5\n"}

        def fake_reader(path: Path) -> str:
            rel = str(path).split(str(tmp_path) + "/", 1)[-1] if str(tmp_path) in str(path) else str(path)
            if rel in file_contents:
                return file_contents[rel]
            raise FileNotFoundError(rel)

        findings_file = tmp_path / "findings.jsonl"
        ctx = CompiledContext(work_dir=tmp_path)
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh, context=ctx, file_reader=fake_reader)
            router.receive({
                "p": "P1", "t": "violation", "d": "d1",
                "file": "src/example.py", "line": 3,
                "w": "Issue", "reason": "Because", "severity": "minor", "req": "R-1",
            })
        written = json.loads(findings_file.read_text().strip())
        assert written["snippet"] == "line3"
        assert ">>> line3" in written["context"]


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
