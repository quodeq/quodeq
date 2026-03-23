"""Tests for incremental analysis — change detection and file classification."""
from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

from quodeq.analysis.incremental import detect_changed_files, ChangeDetectionResult


class TestDetectChangedFiles:
    def _make_fingerprint(self, files_content: dict[str, str], dimension="security"):
        return {
            "dimension": dimension,
            "git_commit": "abc123",
            "file_hashes": {f: hashlib.sha256(c.encode()).hexdigest() for f, c in files_content.items()},
            "standards_checksum": "std_hash_123",
            "timestamp": "2026-01-01",
        }

    def test_detects_changed_file(self, tmp_path):
        prev = self._make_fingerprint({"a.py": "old_content", "b.py": "same"})
        (tmp_path / "a.py").write_text("new_content")
        (tmp_path / "b.py").write_text("same")
        result = detect_changed_files(src=tmp_path, files=["a.py", "b.py"], prev_fingerprint=prev, standards_dir=None, dimension="security")
        assert "a.py" in result.changed
        assert "b.py" not in result.changed

    def test_detects_new_file(self, tmp_path):
        prev = self._make_fingerprint({"a.py": "content"})
        (tmp_path / "a.py").write_text("content")
        (tmp_path / "new.py").write_text("brand new")
        result = detect_changed_files(src=tmp_path, files=["a.py", "new.py"], prev_fingerprint=prev, standards_dir=None, dimension="security")
        assert "new.py" in result.changed
        assert "a.py" not in result.changed

    def test_standards_change_triggers_full(self, tmp_path):
        prev = self._make_fingerprint({"a.py": "content"})
        prev["standards_checksum"] = "old_standards"
        (tmp_path / "a.py").write_text("content")
        standards = tmp_path / "standards" / "compiled"
        standards.mkdir(parents=True)
        (standards / "security.json").write_text('{"new": true}')
        result = detect_changed_files(src=tmp_path, files=["a.py"], prev_fingerprint=prev, standards_dir=tmp_path / "standards", dimension="security")
        assert result.full_reanalysis is True

    def test_no_previous_fingerprint_returns_full(self, tmp_path):
        result = detect_changed_files(src=tmp_path, files=["a.py"], prev_fingerprint=None, standards_dir=None, dimension="security")
        assert result.full_reanalysis is True

    def test_no_changes_returns_empty(self, tmp_path):
        (tmp_path / "a.py").write_text("same")
        prev = self._make_fingerprint({"a.py": "same"})
        result = detect_changed_files(src=tmp_path, files=["a.py"], prev_fingerprint=prev, standards_dir=None, dimension="security")
        assert len(result.changed) == 0
        assert result.full_reanalysis is False
