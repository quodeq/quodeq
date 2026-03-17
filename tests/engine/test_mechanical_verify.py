"""Tests for mechanical verification (snippet-based finding confirmation)."""
from pathlib import Path

import pytest

from quodeq.analysis.subagents.verify import _mechanical_check, run_mechanical_verify


class TestMechanicalCheck:
    def test_file_not_found(self, tmp_path):
        finding = {"file": "nonexistent.py", "line": 1, "snippet": "x = 1"}
        assert _mechanical_check(finding, tmp_path) == "gone"

    def test_no_file_field(self, tmp_path):
        finding = {"line": 1, "snippet": "x = 1"}
        assert _mechanical_check(finding, tmp_path) == "gone"

    def test_empty_file_field(self, tmp_path):
        finding = {"file": "", "line": 1, "snippet": "x = 1"}
        assert _mechanical_check(finding, tmp_path) == "gone"

    def test_exact_line_match(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1\ny = 2\nz = 3\n")
        finding = {"file": "app.py", "line": 2, "snippet": "y = 2"}
        assert _mechanical_check(finding, tmp_path) == "confirmed"

    def test_snippet_in_line(self, tmp_path):
        (tmp_path / "app.py").write_text("    result = compute(x, y)  # important\n")
        finding = {"file": "app.py", "line": 1, "snippet": "compute(x, y)"}
        assert _mechanical_check(finding, tmp_path) == "confirmed"

    def test_line_shifted_nearby(self, tmp_path):
        lines = ["# header\n"] * 5 + ["target_code = True\n"] + ["# footer\n"] * 5
        (tmp_path / "app.py").write_text("".join(lines))
        # Finding says line 3 but code is actually at line 6 — within ±10
        finding = {"file": "app.py", "line": 3, "snippet": "target_code = True"}
        assert _mechanical_check(finding, tmp_path) == "confirmed"

    def test_snippet_not_found(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1\ny = 2\n")
        finding = {"file": "app.py", "line": 1, "snippet": "completely_different"}
        assert _mechanical_check(finding, tmp_path) == "ambiguous"

    def test_no_snippet(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1\n")
        finding = {"file": "app.py", "line": 1, "snippet": ""}
        assert _mechanical_check(finding, tmp_path) == "ambiguous"

    def test_no_snippet_key(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1\n")
        finding = {"file": "app.py", "line": 1}
        assert _mechanical_check(finding, tmp_path) == "ambiguous"


class TestRunMechanicalVerify:
    def test_copies_confirmed_findings(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1\ny = 2\nz = 3\n")
        findings = [
            {"p": "Modularity", "t": "violation", "file": "app.py", "line": 1, "snippet": "x = 1"},
            {"p": "Modularity", "t": "compliance", "file": "gone.py", "line": 1, "snippet": "ok"},
        ]
        output = tmp_path / "output.jsonl"
        confirmed, gone, ambiguous = run_mechanical_verify(tmp_path, findings, output)

        assert confirmed == 1
        assert gone == 1
        assert len(ambiguous) == 0
        assert output.exists()
        lines = output.read_text().strip().split("\n")
        assert len(lines) == 1
        assert '"x = 1"' in lines[0]

    def test_empty_findings(self, tmp_path):
        output = tmp_path / "output.jsonl"
        confirmed, gone, ambiguous = run_mechanical_verify(tmp_path, [], output)
        assert confirmed == 0
        assert gone == 0
        assert len(ambiguous) == 0
