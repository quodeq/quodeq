"""Tests for finding verification (pre-filter + AI verification flow)."""
from pathlib import Path

import pytest

from quodeq.analysis.subagents.verify import (
    _pre_filter_gone,
    _group_by_file,
    _write_verify_manifest,
    build_verify_prompt,
)
import json


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

    def test_file_not_found(self, tmp_path):
        findings = [{"file": "nonexistent.py", "line": 1, "snippet": "x = 1"}]
        surviving, gone = _pre_filter_gone(findings, tmp_path)
        assert gone == 1
        assert surviving == []

    def test_no_file_field(self, tmp_path):
        findings = [{"line": 1, "snippet": "x = 1"}]
        surviving, gone = _pre_filter_gone(findings, tmp_path)
        assert gone == 1
        assert surviving == []

    def test_empty_file_field(self, tmp_path):
        findings = [{"file": "", "line": 1, "snippet": "x = 1"}]
        surviving, gone = _pre_filter_gone(findings, tmp_path)
        assert gone == 1
        assert surviving == []

    def test_file_exists_survives(self, tmp_path):
        """File exists -> finding survives the pre-filter."""
        (tmp_path / "app.py").write_text("x = 1\ny = 2\nz = 3\n")
        findings = [{"file": "app.py", "line": 2, "snippet": "y = 2"}]
        surviving, gone = _pre_filter_gone(findings, tmp_path)
        assert len(surviving) == 1
        assert gone == 0

    def test_mixed_existing_and_gone(self, tmp_path):
        """Surviving findings need AI verification, gone ones are dropped."""
        (tmp_path / "app.py").write_text("x = 1\ny = 2\nz = 3\n")
        findings = [
            {"p": "Mod", "t": "violation", "file": "app.py", "line": 1, "snippet": "x = 1"},
            {"p": "Mod", "t": "compliance", "file": "gone.py", "line": 1, "snippet": "ok"},
        ]
        surviving, gone = _pre_filter_gone(findings, tmp_path)
        assert gone == 1
        assert len(surviving) == 1
        assert surviving[0]["file"] == "app.py"


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
