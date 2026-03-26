"""Tests for carry-forward findings and fingerprint-aware verification step."""
from pathlib import Path
from unittest.mock import patch, MagicMock

import hashlib
import json
import pytest

from quodeq.analysis.subagents.verify import (
    write_carry_forward_findings,
)


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
        """Empty list -> returns 0, no file created."""
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

    @patch("quodeq.analysis.subagents._verification._run_verification_pool")
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

    @patch("quodeq.analysis.subagents._verification._run_verification_pool")
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
