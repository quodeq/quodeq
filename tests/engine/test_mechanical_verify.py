"""Tests for finding verification (pre-filter + AI verification flow)."""
from pathlib import Path
import hashlib
import json
import pytest

from quodeq.analysis.subagents.verify import (
    _pre_filter_gone,
    _group_by_file,
    _write_verify_manifest,
    build_verify_prompt,
    partition_findings_by_fingerprint,
)


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


class TestPartitionFindingsByFingerprint:
    """Tests for partition_findings_by_fingerprint."""

    def _make_findings(self, files: list[str]) -> list[dict]:
        """Helper: create one finding per file."""
        return [{"p": "Mod", "t": "violation", "file": f, "line": 1, "reason": "test"} for f in files]

    def test_no_fingerprint_all_need_verification(self, tmp_path):
        """No previous fingerprint → all findings need verification."""
        findings = self._make_findings(["a.py", "b.py"])
        carry, verify = partition_findings_by_fingerprint(findings, None, tmp_path)
        assert carry == []
        assert verify == findings

    def test_all_files_unchanged(self, tmp_path):
        """All files have matching hashes → all carried forward."""
        (tmp_path / "a.py").write_text("content_a")
        (tmp_path / "b.py").write_text("content_b")
        fp = {
            "file_hashes": {
                "a.py": hashlib.sha256(b"content_a").hexdigest(),
                "b.py": hashlib.sha256(b"content_b").hexdigest(),
            },
            "standards_checksum": None,
        }
        findings = self._make_findings(["a.py", "b.py"])
        carry, verify = partition_findings_by_fingerprint(findings, fp, tmp_path)
        assert len(carry) == 2
        assert verify == []

    def test_all_files_changed(self, tmp_path):
        """All files have different hashes → all need verification."""
        (tmp_path / "a.py").write_text("new_content")
        fp = {"file_hashes": {"a.py": "old_hash"}, "standards_checksum": None}
        findings = self._make_findings(["a.py"])
        carry, verify = partition_findings_by_fingerprint(findings, fp, tmp_path)
        assert carry == []
        assert len(verify) == 1

    def test_mixed_changed_unchanged(self, tmp_path):
        """Mix of changed and unchanged → correct split."""
        (tmp_path / "unchanged.py").write_text("same")
        (tmp_path / "changed.py").write_text("new_content")
        fp = {
            "file_hashes": {
                "unchanged.py": hashlib.sha256(b"same").hexdigest(),
                "changed.py": "old_hash",
            },
            "standards_checksum": None,
        }
        findings = self._make_findings(["unchanged.py", "changed.py"])
        carry, verify = partition_findings_by_fingerprint(findings, fp, tmp_path)
        assert len(carry) == 1
        assert carry[0]["file"] == "unchanged.py"
        assert len(verify) == 1
        assert verify[0]["file"] == "changed.py"

    def test_file_deleted(self, tmp_path):
        """File no longer exists → needs verification (will be caught by pre_filter_gone)."""
        fp = {"file_hashes": {"gone.py": "some_hash"}, "standards_checksum": None}
        findings = self._make_findings(["gone.py"])
        carry, verify = partition_findings_by_fingerprint(findings, fp, tmp_path)
        assert carry == []
        assert len(verify) == 1

    def test_file_not_in_fingerprint(self, tmp_path):
        """File not tracked in previous fingerprint → needs verification."""
        (tmp_path / "new.py").write_text("content")
        fp = {"file_hashes": {}, "standards_checksum": None}
        findings = self._make_findings(["new.py"])
        carry, verify = partition_findings_by_fingerprint(findings, fp, tmp_path)
        assert carry == []
        assert len(verify) == 1

    def test_finding_with_empty_file_field(self, tmp_path):
        """Finding with empty/missing file field → needs verification."""
        fp = {"file_hashes": {}, "standards_checksum": None}
        findings = [
            {"p": "Mod", "t": "violation", "file": "", "line": 1, "reason": "empty"},
            {"p": "Mod", "t": "violation", "line": 1, "reason": "missing"},
        ]
        carry, verify = partition_findings_by_fingerprint(findings, fp, tmp_path)
        assert carry == []
        assert len(verify) == 2

    def test_standards_changed_all_need_verification(self, tmp_path):
        """Standards checksum differs → all need verification regardless of file hashes."""
        (tmp_path / "a.py").write_text("content_a")
        # File hash matches, but standards changed
        fp = {
            "file_hashes": {"a.py": hashlib.sha256(b"content_a").hexdigest()},
            "standards_checksum": "old_standards_hash",
        }
        standards_dir = tmp_path / "standards" / "compiled"
        standards_dir.mkdir(parents=True)
        (standards_dir / "security.json").write_text('{"new": "standards"}')
        findings = self._make_findings(["a.py"])
        carry, verify = partition_findings_by_fingerprint(
            findings, fp, tmp_path,
            standards_dir=tmp_path / "standards", dimension="security",
        )
        assert carry == []
        assert len(verify) == 1

    def test_standards_unchanged_uses_file_hashes(self, tmp_path):
        """Standards checksum matches → partition normally by file hashes."""
        (tmp_path / "a.py").write_text("content_a")
        std_content = b'{"same": "standards"}'
        standards_dir = tmp_path / "standards" / "compiled"
        standards_dir.mkdir(parents=True)
        (standards_dir / "security.json").write_bytes(std_content)
        fp = {
            "file_hashes": {"a.py": hashlib.sha256(b"content_a").hexdigest()},
            "standards_checksum": hashlib.sha256(std_content).hexdigest(),
        }
        findings = self._make_findings(["a.py"])
        carry, verify = partition_findings_by_fingerprint(
            findings, fp, tmp_path,
            standards_dir=tmp_path / "standards", dimension="security",
        )
        assert len(carry) == 1
        assert verify == []


