"""Tests for quodeq.analysis.subagents._heartbeat — progress reporting."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestClassifyJsonlLine:
    def test_violation(self):
        from quodeq.analysis.subagents._heartbeat import _classify_jsonl_line, FindingCounts
        counts = FindingCounts()
        _classify_jsonl_line(json.dumps({"t": "violation"}), counts)
        assert counts.total == 1
        assert counts.violations == 1

    def test_compliance(self):
        from quodeq.analysis.subagents._heartbeat import _classify_jsonl_line, FindingCounts
        counts = FindingCounts()
        _classify_jsonl_line(json.dumps({"t": "compliance"}), counts)
        assert counts.total == 1
        assert counts.compliances == 1

    def test_other_type(self):
        from quodeq.analysis.subagents._heartbeat import _classify_jsonl_line, FindingCounts
        counts = FindingCounts()
        _classify_jsonl_line(json.dumps({"t": "info"}), counts)
        assert counts.total == 1
        assert counts.violations == 0
        assert counts.compliances == 0

    def test_invalid_json(self):
        from quodeq.analysis.subagents._heartbeat import _classify_jsonl_line, FindingCounts
        counts = FindingCounts()
        _classify_jsonl_line("not json", counts)
        assert counts.total == 1


class TestReadFindingsFromFile:
    def test_reads_findings(self, tmp_path):
        from quodeq.analysis.subagents._heartbeat import _read_findings_from_file
        p = tmp_path / "findings.jsonl"
        p.write_text(
            json.dumps({"t": "violation"}) + "\n"
            + json.dumps({"t": "compliance"}) + "\n"
            + "\n"
        )
        counts = _read_findings_from_file(p)
        assert counts.total == 2
        assert counts.violations == 1
        assert counts.compliances == 1


class TestCountJsonlFindings:
    def test_file_not_exists(self, tmp_path):
        from quodeq.analysis.subagents._heartbeat import _count_jsonl_findings
        lock = threading.Lock()
        counts = _count_jsonl_findings(tmp_path / "missing.jsonl", lock)
        assert counts.total == 0

    def test_with_valid_file(self, tmp_path):
        from quodeq.analysis.subagents._heartbeat import _count_jsonl_findings
        p = tmp_path / "findings.jsonl"
        p.write_text(json.dumps({"t": "violation"}) + "\n")
        lock = threading.Lock()
        counts = _count_jsonl_findings(p, lock)
        assert counts.total == 1
        assert counts.violations == 1

    def test_os_error(self, tmp_path):
        from quodeq.analysis.subagents._heartbeat import _count_jsonl_findings
        lock = threading.Lock()
        with patch("quodeq.analysis.subagents._heartbeat._read_findings_from_file", side_effect=OSError("err")):
            p = tmp_path / "findings.jsonl"
            p.write_text("data")
            counts = _count_jsonl_findings(p, lock)
            assert counts.total == 0


class TestFindingCounts:
    def test_defaults(self):
        from quodeq.analysis.subagents._heartbeat import FindingCounts
        c = FindingCounts()
        assert c.total == 0
        assert c.violations == 0
        assert c.compliances == 0


class TestHeartbeatContext:
    def test_creation(self, tmp_path):
        from quodeq.analysis.subagents._heartbeat import HeartbeatContext
        ctx = HeartbeatContext(
            queue_path=tmp_path / "queue",
            dimension_key="security",
            jsonl_path=tmp_path / "findings.jsonl",
            lock=threading.Lock(),
        )
        assert ctx.dimension_key == "security"
