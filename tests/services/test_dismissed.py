"""Tests for the dismissed findings storage service."""
import json
from pathlib import Path

from quodeq.services.dismissed import (
    load_dismissed,
    dismiss_finding,
    restore_finding,
    dismissed_keys,
)


class TestDismissedStorage:
    def test_load_empty_when_no_file(self, tmp_path):
        result = load_dismissed(tmp_path / "nonexistent")
        assert result == []

    def test_dismiss_creates_file_and_appends(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        finding = {"req": "M-MOD-4", "file": "foo.js", "line": 4, "dimension": "maintainability", "severity": "minor"}
        dismiss_finding(project_dir, finding)
        result = load_dismissed(project_dir)
        assert len(result) == 1
        assert result[0]["req"] == "M-MOD-4"
        assert result[0]["file"] == "foo.js"
        assert result[0]["line"] == 4
        assert "dismissed_at" in result[0]

    def test_dismiss_deduplicates(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        finding = {"req": "M-MOD-4", "file": "foo.js", "line": 4, "dimension": "maintainability", "severity": "minor"}
        dismiss_finding(project_dir, finding)
        dismiss_finding(project_dir, finding)
        result = load_dismissed(project_dir)
        assert len(result) == 1

    def test_restore_removes_finding(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        dismiss_finding(project_dir, {"req": "M-MOD-4", "file": "foo.js", "line": 4, "dimension": "maintainability", "severity": "minor"})
        dismiss_finding(project_dir, {"req": "S-CON-1", "file": "bar.py", "line": 10, "dimension": "security", "severity": "major"})
        restore_finding(project_dir, {"req": "M-MOD-4", "file": "foo.js", "line": 4})
        result = load_dismissed(project_dir)
        assert len(result) == 1
        assert result[0]["req"] == "S-CON-1"

    def test_restore_nonexistent_is_noop(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        restore_finding(project_dir, {"req": "X-X-1", "file": "x.py", "line": 1})
        assert load_dismissed(project_dir) == []

    def test_dismissed_keys_returns_set_of_tuples(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        dismiss_finding(project_dir, {"req": "M-MOD-4", "file": "foo.js", "line": 4, "dimension": "maintainability", "severity": "minor"})
        keys = dismissed_keys(project_dir)
        assert keys == {("M-MOD-4", "foo.js", 4)}
