"""Tests for quodeq.analysis.subagents._verify_io — evidence path resolution and JSONL parsing."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestParseFindingLine:
    def test_empty_line(self):
        from quodeq.analysis.subagents._verify_io import _parse_finding_line
        assert _parse_finding_line("") is None
        assert _parse_finding_line("  ") is None

    def test_invalid_json(self):
        from quodeq.analysis.subagents._verify_io import _parse_finding_line
        assert _parse_finding_line("{bad") is None

    def test_missing_principle(self):
        from quodeq.analysis.subagents._verify_io import _parse_finding_line
        assert _parse_finding_line(json.dumps({"t": "violation"})) is None

    def test_invalid_type(self):
        from quodeq.analysis.subagents._verify_io import _parse_finding_line
        assert _parse_finding_line(json.dumps({"p": "P1", "t": "info"})) is None

    def test_valid_violation(self):
        from quodeq.analysis.subagents._verify_io import _parse_finding_line
        result = _parse_finding_line(json.dumps({"p": "P1", "t": "violation"}))
        assert result is not None
        assert result["p"] == "P1"

    def test_valid_compliance(self):
        from quodeq.analysis.subagents._verify_io import _parse_finding_line
        result = _parse_finding_line(json.dumps({"p": "P2", "t": "compliance"}))
        assert result is not None


class TestLoadPreviousFindings:
    def test_file_not_exists(self, tmp_path):
        from quodeq.analysis.subagents._verify_io import _load_previous_findings
        result = _load_previous_findings(tmp_path / "missing.jsonl")
        assert result == []

    def test_valid_jsonl(self, tmp_path):
        from quodeq.analysis.subagents._verify_io import _load_previous_findings
        p = tmp_path / "findings.jsonl"
        p.write_text(
            json.dumps({"p": "P1", "t": "violation"}) + "\n"
            + json.dumps({"p": "P2", "t": "compliance"}) + "\n"
            + "bad json\n"
            + "\n"
        )
        result = _load_previous_findings(p)
        assert len(result) == 2

    def test_os_error(self, tmp_path):
        from quodeq.analysis.subagents._verify_io import _load_previous_findings
        p = tmp_path / "findings.jsonl"
        p.write_text("data")
        def _raise(path):
            raise OSError("read error")
        result = _load_previous_findings(p, open_fn=_raise)
        assert result == []


class TestResolveEvidencePaths:
    def test_valid_path(self, tmp_path):
        from quodeq.analysis.subagents._verify_io import resolve_evidence_paths
        evidence_dir = tmp_path / "proj-uuid" / "run-id" / "evidence"
        evidence_dir.mkdir(parents=True)
        result = resolve_evidence_paths(evidence_dir)
        assert result is not None
        run_id, project_uuid, reports_base = result
        assert run_id == "run-id"
        assert project_uuid == "proj-uuid"

    def test_invalid_path(self, tmp_path):
        from quodeq.analysis.subagents._verify_io import resolve_evidence_paths
        result = resolve_evidence_paths(tmp_path / "no-evidence-dir")
        assert result is None


class TestFindPreviousEvidence:
    def test_no_previous_runs(self, tmp_path):
        from quodeq.analysis.subagents._verify_io import _find_previous_evidence
        with patch("quodeq.analysis.subagents._verify_io.list_runs", return_value=[]):
            result = _find_previous_evidence(tmp_path, "proj", "current", "security")
            assert result is None

    def test_skips_current_run(self, tmp_path):
        from quodeq.analysis.subagents._verify_io import _find_previous_evidence
        run = MagicMock()
        run.run_id = "current"
        with patch("quodeq.analysis.subagents._verify_io.list_runs", return_value=[run]):
            result = _find_previous_evidence(tmp_path, "proj", "current", "security")
            assert result is None

    def test_skips_run_without_eval(self, tmp_path):
        from quodeq.analysis.subagents._verify_io import _find_previous_evidence
        run = MagicMock()
        run.run_id = "prev"
        (tmp_path / "proj" / "prev").mkdir(parents=True)
        with patch("quodeq.analysis.subagents._verify_io.list_runs", return_value=[run]):
            result = _find_previous_evidence(tmp_path, "proj", "current", "security")
            assert result is None

    def test_finds_valid_previous(self, tmp_path):
        from quodeq.analysis.subagents._verify_io import _find_previous_evidence
        run = MagicMock()
        run.run_id = "prev"
        run_dir = tmp_path / "proj" / "prev"
        (run_dir / "evaluation").mkdir(parents=True)
        (run_dir / "evaluation" / "security.json").write_text("{}")
        (run_dir / "evidence").mkdir(parents=True)
        jsonl = run_dir / "evidence" / "security_evidence.jsonl"
        jsonl.write_text('{"p":"P1","t":"violation"}\n')
        with patch("quodeq.analysis.subagents._verify_io.list_runs", return_value=[run]):
            result = _find_previous_evidence(tmp_path, "proj", "current", "security")
            assert result == jsonl


class TestResolvePreviousEvidence:
    def test_no_evidence_paths(self, tmp_path):
        from quodeq.analysis.subagents._verify_io import _resolve_previous_evidence
        cache = {}
        path, cached = _resolve_previous_evidence(tmp_path, "dim", cache, ("key", "val"))
        assert path is None
        assert ("key", "val") in cache

    def test_no_previous_evidence(self, tmp_path):
        from quodeq.analysis.subagents._verify_io import _resolve_previous_evidence
        evidence_dir = tmp_path / "proj" / "run" / "evidence"
        evidence_dir.mkdir(parents=True)
        cache = {}
        with patch("quodeq.analysis.subagents._verify_io._find_previous_evidence", return_value=None):
            path, cached = _resolve_previous_evidence(evidence_dir, "dim", cache, ("k", "v"))
            assert path is None
            assert ("k", "v") in cache
