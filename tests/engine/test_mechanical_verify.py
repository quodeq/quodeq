"""Tests for finding verification (pre-filter + AI verification flow)."""
from pathlib import Path
from unittest.mock import patch, MagicMock

import hashlib
import json
import pytest

from quodeq.analysis.subagents.verify import (
    _pre_filter_gone,
    _group_by_file,
    _write_verify_manifest,
    build_verify_prompt,
    partition_findings_by_fingerprint,
    write_carry_forward_findings,
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


class TestWriteCarryForwardFindings:
    def test_creates_file_if_missing(self, tmp_path):
        """Creates the JSONL file and writes findings."""
        findings = [
            {"p": "Mod", "t": "violation", "file": "a.py", "line": 1, "reason": "test"},
            {"p": "Mod", "t": "compliance", "file": "b.py", "line": 2, "reason": "ok"},
        ]
        count = write_carry_forward_findings(findings, tmp_path, "security")
        assert count == 2
        jsonl = tmp_path / "security_evidence.jsonl"
        assert jsonl.exists()
        lines = [l for l in jsonl.read_text().splitlines() if l.strip()]
        assert len(lines) == 2
        assert json.loads(lines[0])["file"] == "a.py"
        assert json.loads(lines[1])["file"] == "b.py"

    def test_appends_to_existing_file(self, tmp_path):
        """Appends to existing JSONL without overwriting."""
        jsonl = tmp_path / "security_evidence.jsonl"
        jsonl.write_text('{"p":"Exist","t":"violation","file":"x.py","line":1}\n')
        findings = [{"p": "Mod", "t": "violation", "file": "a.py", "line": 1, "reason": "new"}]
        count = write_carry_forward_findings(findings, tmp_path, "security")
        assert count == 1
        lines = [l for l in jsonl.read_text().splitlines() if l.strip()]
        assert len(lines) == 2  # original + new
        assert json.loads(lines[0])["file"] == "x.py"  # original preserved
        assert json.loads(lines[1])["file"] == "a.py"   # new appended

    def test_empty_findings(self, tmp_path):
        """Empty list → returns 0, no file created."""
        count = write_carry_forward_findings([], tmp_path, "security")
        assert count == 0


class TestRunVerificationStepFingerprint:
    """Integration tests for _run_verification_step with fingerprint awareness."""

    def _make_config(self, tmp_path, *, incremental=False, file_filter=None, verify=True):
        """Create a minimal mock config for testing."""
        config = MagicMock()
        config.src = tmp_path / "src"
        config.src.mkdir(exist_ok=True)
        config.options.verify_findings = verify
        config.options.incremental = incremental
        config.options.incremental_file_filter = file_filter
        config.standards_dir = None
        return config

    @patch("quodeq.analysis.subagents.runner._run_verification_pool")
    @patch("quodeq.analysis.subagents.verify.load_previous_findings_for_dimension")
    @patch("quodeq.analysis.fingerprint.find_previous_fingerprint")
    def test_unchanged_files_carried_forward_not_sent_to_pool(
        self, mock_find_fp, mock_load_findings, mock_pool, tmp_path,
    ):
        """Findings for unchanged files are written to JSONL, not sent to AI pool."""
        src = tmp_path / "src"
        src.mkdir(exist_ok=True)
        (src / "unchanged.py").write_text("same_content")
        (src / "changed.py").write_text("new_content")

        unchanged_hash = hashlib.sha256(b"same_content").hexdigest()
        findings = [
            {"p": "Mod", "t": "violation", "file": "unchanged.py", "line": 1, "reason": "r1"},
            {"p": "Mod", "t": "violation", "file": "changed.py", "line": 1, "reason": "r2"},
        ]
        fingerprint = {
            "dimension": "security",
            "file_hashes": {"unchanged.py": unchanged_hash, "changed.py": "old_hash"},
            "standards_checksum": None,
        }

        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir(parents=True)

        config = self._make_config(tmp_path)
        config.src = src

        mock_load_findings.return_value = findings
        mock_find_fp.return_value = (fingerprint, None)
        mock_pool.return_value = []

        from quodeq.analysis.subagents.runner import _run_verification_step
        _run_verification_step(config, "security", evidence_dir, ["unchanged.py", "changed.py"])

        # Pool should only receive the changed file
        assert mock_pool.called
        files_to_verify = mock_pool.call_args[0][3]
        assert "unchanged.py" not in files_to_verify
        assert "changed.py" in files_to_verify

        # Carried forward findings should be in JSONL
        output_jsonl = evidence_dir / "security_evidence.jsonl"
        assert output_jsonl.exists()
        lines = [json.loads(l) for l in output_jsonl.read_text().splitlines() if l.strip()]
        unchanged_findings = [l for l in lines if l.get("file") == "unchanged.py"]
        assert len(unchanged_findings) == 1

    @patch("quodeq.analysis.subagents.runner._run_verification_pool")
    @patch("quodeq.analysis.subagents.verify.load_previous_findings_for_dimension")
    @patch("quodeq.analysis.fingerprint.find_previous_fingerprint")
    def test_incremental_filters_to_file_filter_only(
        self, mock_find_fp, mock_load_findings, mock_pool, tmp_path,
    ):
        """With incremental_file_filter, only those files' findings are considered."""
        src = tmp_path / "src"
        src.mkdir(exist_ok=True)
        (src / "changed.py").write_text("new_content")
        (src / "unchanged.py").write_text("same")

        findings = [
            {"p": "Mod", "t": "violation", "file": "changed.py", "line": 1, "reason": "r1"},
            {"p": "Mod", "t": "violation", "file": "unchanged.py", "line": 1, "reason": "r2"},
        ]
        fingerprint = {
            "dimension": "security",
            "file_hashes": {
                "changed.py": "old_hash",
                "unchanged.py": hashlib.sha256(b"same").hexdigest(),
            },
            "standards_checksum": None,
        }

        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir(parents=True)

        config = self._make_config(tmp_path, incremental=True, file_filter={"changed.py"})
        config.src = src

        mock_load_findings.return_value = findings
        mock_find_fp.return_value = (fingerprint, None)
        mock_pool.return_value = []

        from quodeq.analysis.subagents.runner import _run_verification_step
        _run_verification_step(config, "security", evidence_dir, ["changed.py", "unchanged.py"])

        # JSONL should NOT have unchanged.py findings (that's _maybe_carry_forward's job)
        output_jsonl = evidence_dir / "security_evidence.jsonl"
        if output_jsonl.exists():
            lines = [json.loads(l) for l in output_jsonl.read_text().splitlines() if l.strip()]
            unchanged_findings = [l for l in lines if l.get("file") == "unchanged.py"]
            assert len(unchanged_findings) == 0
