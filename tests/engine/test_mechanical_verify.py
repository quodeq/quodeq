"""Tests for finding verification (pre-filter + AI verification flow)."""
from pathlib import Path

import pytest

from quodeq.analysis.subagents.verify import (
    _mechanical_check,
    _pre_filter_gone,
    _group_by_file,
    _write_verify_manifest,
    build_verify_prompt,
    run_mechanical_verify,
    write_verified_findings,
)
import json


class TestMechanicalCheck:
    """_mechanical_check now only checks file existence — everything
    that isn't 'gone' is 'ambiguous' (routed to AI verification)."""

    def test_file_not_found(self, tmp_path):
        finding = {"file": "nonexistent.py", "line": 1, "snippet": "x = 1"}
        assert _mechanical_check(finding, tmp_path) == "gone"

    def test_no_file_field(self, tmp_path):
        finding = {"line": 1, "snippet": "x = 1"}
        assert _mechanical_check(finding, tmp_path) == "gone"

    def test_empty_file_field(self, tmp_path):
        finding = {"file": "", "line": 1, "snippet": "x = 1"}
        assert _mechanical_check(finding, tmp_path) == "gone"

    def test_file_exists_returns_ambiguous(self, tmp_path):
        """File exists → needs AI verification, not mechanical confirmation."""
        (tmp_path / "app.py").write_text("x = 1\ny = 2\nz = 3\n")
        finding = {"file": "app.py", "line": 2, "snippet": "y = 2"}
        assert _mechanical_check(finding, tmp_path) == "ambiguous"

    def test_file_exists_no_snippet_returns_ambiguous(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1\n")
        finding = {"file": "app.py", "line": 1}
        assert _mechanical_check(finding, tmp_path) == "ambiguous"


class TestPreFilterGone:
    def test_drops_missing_files(self, tmp_path):
        (tmp_path / "exists.py").write_text("x = 1\n")
        findings = [
            {"file": "exists.py", "line": 1},
            {"file": "gone.py", "line": 1},
            {"file": "", "line": 1},
        ]
        surviving, gone = _pre_filter_gone(findings, tmp_path)
        assert len(surviving) == 1
        assert surviving[0]["file"] == "exists.py"
        assert gone == 2

    def test_empty_findings(self, tmp_path):
        surviving, gone = _pre_filter_gone([], tmp_path)
        assert surviving == []
        assert gone == 0


class TestGroupByFile:
    def test_groups_findings(self):
        findings = [
            {"file": "a.py", "reason": "r1"},
            {"file": "b.py", "reason": "r2"},
            {"file": "a.py", "reason": "r3"},
        ]
        grouped = _group_by_file(findings)
        assert len(grouped) == 2
        assert len(grouped["a.py"]) == 2
        assert len(grouped["b.py"]) == 1


class TestVerifyManifest:
    def test_writes_manifest(self, tmp_path):
        grouped = {"a.py": [{"reason": "r1"}], "b.py": [{"reason": "r2"}]}
        path = tmp_path / "manifest.json"
        _write_verify_manifest(grouped, path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert "a.py" in data
        assert "b.py" in data


class TestBuildVerifyPrompt:
    def test_includes_manifest_path(self, tmp_path):
        manifest = tmp_path / "manifest.json"
        prompt = build_verify_prompt(manifest, "maintainability")
        assert str(manifest) in prompt
        assert "maintainability" in prompt
        assert "report_finding" in prompt


class TestRunMechanicalVerify:
    def test_all_surviving_are_ambiguous(self, tmp_path):
        """With AI verification, mechanical verify returns no confirmed —
        all surviving findings are ambiguous (need AI)."""
        (tmp_path / "app.py").write_text("x = 1\ny = 2\nz = 3\n")
        findings = [
            {"p": "Mod", "t": "violation", "file": "app.py", "line": 1, "snippet": "x = 1"},
            {"p": "Mod", "t": "compliance", "file": "gone.py", "line": 1, "snippet": "ok"},
        ]
        confirmed, gone, ambiguous = run_mechanical_verify(tmp_path, findings)
        assert len(confirmed) == 0  # no mechanical confirmations
        assert gone == 1
        assert len(ambiguous) == 1  # surviving findings need AI verification

    def test_empty_findings(self, tmp_path):
        confirmed, gone, ambiguous = run_mechanical_verify(tmp_path, [])
        assert len(confirmed) == 0
        assert gone == 0
        assert len(ambiguous) == 0


class TestWriteVerifiedFindings:
    def test_writes_to_jsonl(self, tmp_path):
        output = tmp_path / "output.jsonl"
        findings = [
            {"p": "Mod", "t": "violation", "file": "app.py", "line": 1, "snippet": "x = 1"},
        ]
        write_verified_findings(findings, output)
        assert output.exists()
        lines = output.read_text().strip().split("\n")
        assert len(lines) == 1
        assert '"x = 1"' in lines[0]

    def test_empty_findings_no_file(self, tmp_path):
        output = tmp_path / "output.jsonl"
        write_verified_findings([], output)
        assert not output.exists()
