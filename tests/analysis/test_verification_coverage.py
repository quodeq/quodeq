"""Tests for analysis.subagents._verification — verification pipeline helpers."""
from __future__ import annotations

from copy import copy
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from quodeq.analysis._types import AnalysisOptions, RunConfig


# ---------------------------------------------------------------------------
# _load_and_filter_previous
# ---------------------------------------------------------------------------

class TestLoadAndFilterPrevious:
    def _make_config(self, tmp_path: Path, incremental_filter=None) -> RunConfig:
        opts = AnalysisOptions(incremental_file_filter=incremental_filter)
        return RunConfig(src=tmp_path, language="python", options=opts)

    @patch("quodeq.services.dismissed.dismissed_keys", return_value=set())
    @patch("quodeq.analysis.subagents.verify.load_previous_findings_for_dimension")
    def test_returns_empty_when_no_previous(self, mock_load, mock_dk, tmp_path):
        from quodeq.analysis.subagents._verification import _load_and_filter_previous
        mock_load.return_value = []
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        result = _load_and_filter_previous(self._make_config(tmp_path), "security", evidence_dir)
        assert result == []

    @patch("quodeq.services.dismissed.dismissed_keys", return_value=set())
    @patch("quodeq.analysis.subagents.verify.load_previous_findings_for_dimension")
    def test_returns_all_findings_no_filter(self, mock_load, mock_dk, tmp_path):
        from quodeq.analysis.subagents._verification import _load_and_filter_previous
        findings = [{"file": "a.py", "p": "p1", "line": 1}, {"file": "b.py", "p": "p2", "line": 2}]
        mock_load.return_value = findings
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        result = _load_and_filter_previous(self._make_config(tmp_path), "security", evidence_dir)
        assert len(result) == 2

    @patch("quodeq.services.dismissed.dismissed_keys", return_value=set())
    @patch("quodeq.analysis.subagents.verify.load_previous_findings_for_dimension")
    def test_applies_incremental_file_filter(self, mock_load, mock_dk, tmp_path):
        from quodeq.analysis.subagents._verification import _load_and_filter_previous
        findings = [{"file": "a.py", "p": "p1", "line": 1}, {"file": "b.py", "p": "p2", "line": 2}]
        mock_load.return_value = findings
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        config = self._make_config(tmp_path, incremental_filter={"a.py"})
        result = _load_and_filter_previous(config, "security", evidence_dir)
        assert len(result) == 1
        assert result[0]["file"] == "a.py"

    @patch("quodeq.services.dismissed.dismissed_keys")
    @patch("quodeq.analysis.subagents.verify.load_previous_findings_for_dimension")
    def test_filters_dismissed_findings(self, mock_load, mock_dk, tmp_path):
        from quodeq.analysis.subagents._verification import _load_and_filter_previous
        findings = [
            {"file": "a.py", "p": "p1", "line": 1},
            {"file": "b.py", "p": "p2", "line": 2},
        ]
        mock_load.return_value = findings
        mock_dk.return_value = {("p1", "a.py", 1)}
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        result = _load_and_filter_previous(self._make_config(tmp_path), "security", evidence_dir)
        assert len(result) == 1
        assert result[0]["file"] == "b.py"


# ---------------------------------------------------------------------------
# _dispatch_verification_pool
# ---------------------------------------------------------------------------

class TestDispatchVerificationPool:
    @patch("quodeq.analysis.subagents._verify_pool.run_verification_pool")
    @patch("quodeq.analysis.subagents.verify._write_verify_manifest")
    @patch("quodeq.analysis.subagents.verify._group_by_file")
    def test_dispatches_pool(self, mock_group, mock_write, mock_pool, tmp_path):
        from quodeq.analysis.subagents._verification import _dispatch_verification_pool
        mock_group.return_value = {"a.py": [{"file": "a.py"}]}
        mock_pool.return_value = [{"status": "ok"}]
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        config = RunConfig(src=tmp_path, language="python")
        result = _dispatch_verification_pool(config, "security", evidence_dir, [{"file": "a.py"}])
        assert result == [{"status": "ok"}]
        mock_write.assert_called_once()
        mock_pool.assert_called_once()


# ---------------------------------------------------------------------------
# _dispatch_mini_verify
# ---------------------------------------------------------------------------

class TestDispatchMiniVerify:
    def test_empty_findings_returns_empty(self, tmp_path):
        from quodeq.analysis.subagents._verification import _dispatch_mini_verify
        config = RunConfig(src=tmp_path, language="python")
        result = _dispatch_mini_verify(config, "security", tmp_path, [])
        assert result == []

    @patch("quodeq.analysis.subagents._verify_pool.run_verification_pool")
    @patch("quodeq.analysis.subagents.verify._write_verify_manifest")
    @patch("quodeq.analysis.subagents.verify._group_by_file")
    def test_mini_verify_caps_agents_and_budget(self, mock_group, mock_write, mock_pool, tmp_path):
        from quodeq.analysis.subagents._verification import (
            _dispatch_mini_verify, _MINI_VERIFY_MAX_AGENTS, _MINI_VERIFY_MAX_TIMEOUT,
        )
        mock_group.return_value = {"a.py": [{"file": "a.py"}]}
        mock_pool.return_value = [{"ok": True}]
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        opts = AnalysisOptions(max_subagents=10, pool_budget=9999)
        config = RunConfig(src=tmp_path, language="python", options=opts)
        result = _dispatch_mini_verify(config, "security", evidence_dir, [{"file": "a.py"}])
        assert result == [{"ok": True}]
        actual_config = mock_pool.call_args[0][0]
        assert actual_config.options.max_subagents <= _MINI_VERIFY_MAX_AGENTS
        assert actual_config.options.pool_budget <= _MINI_VERIFY_MAX_TIMEOUT


# ---------------------------------------------------------------------------
# _run_verification_step
# ---------------------------------------------------------------------------

class TestRunVerificationStep:
    @patch("quodeq.services.dismissed.dismissed_keys", return_value=set())
    @patch("quodeq.analysis.subagents.verify.load_previous_findings_for_dimension", return_value=[])
    def test_returns_empty_when_no_previous(self, mock_load, mock_dk, tmp_path):
        from quodeq.analysis.subagents._verification import _run_verification_step
        config = RunConfig(src=tmp_path, language="python")
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        result = _run_verification_step(config, "security", evidence_dir, ["a.py"])
        assert result == []

    @patch("quodeq.analysis.subagents._verify_pool.run_verification_pool", return_value=[])
    @patch("quodeq.analysis.subagents.verify.write_carry_forward_findings", return_value=3)
    @patch("quodeq.analysis.subagents.verify.partition_findings_by_fingerprint")
    @patch("quodeq.services.dismissed.dismissed_keys", return_value=set())
    @patch("quodeq.analysis.subagents.verify.load_previous_findings_for_dimension")
    def test_carry_forward_only(self, mock_load, mock_dk, mock_partition, mock_write_cf, mock_pool, tmp_path):
        from quodeq.analysis.subagents._verification import _run_verification_step
        mock_load.return_value = [{"file": "a.py", "p": "", "line": 0}]
        mock_partition.return_value = ([{"file": "a.py"}], [])
        config = RunConfig(src=tmp_path, language="python")
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        result = _run_verification_step(config, "security", evidence_dir, ["a.py"], prev_fingerprint={})
        assert result == []
        mock_write_cf.assert_called_once()

    @patch("quodeq.analysis.subagents._verify_pool.run_verification_pool", return_value=[{"verified": True}])
    @patch("quodeq.analysis.subagents.verify._write_verify_manifest")
    @patch("quodeq.analysis.subagents.verify._group_by_file", return_value={"b.py": [{"file": "b.py"}]})
    @patch("quodeq.analysis.subagents.verify.write_carry_forward_findings", return_value=1)
    @patch("quodeq.analysis.subagents.verify.partition_findings_by_fingerprint")
    @patch("quodeq.services.dismissed.dismissed_keys", return_value=set())
    @patch("quodeq.analysis.subagents.verify.load_previous_findings_for_dimension")
    def test_mixed_carry_forward_and_verify(self, mock_load, mock_dk, mock_partition, mock_write_cf, mock_group, mock_write_m, mock_pool, tmp_path):
        from quodeq.analysis.subagents._verification import _run_verification_step
        mock_load.return_value = [{"file": "a.py", "p": "", "line": 0}, {"file": "b.py", "p": "", "line": 0}]
        mock_partition.return_value = ([{"file": "a.py"}], [{"file": "b.py"}])
        config = RunConfig(src=tmp_path, language="python")
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        result = _run_verification_step(config, "security", evidence_dir, ["a.py", "b.py"], prev_fingerprint={})
        assert result == [{"verified": True}]

    @patch("quodeq.analysis.subagents._verify_pool.run_verification_pool", return_value=[])
    @patch("quodeq.analysis.subagents.verify._write_verify_manifest")
    @patch("quodeq.analysis.subagents.verify._group_by_file", return_value={"a.py": [{"file": "a.py"}]})
    @patch("quodeq.analysis.subagents.verify.write_carry_forward_findings", return_value=0)
    @patch("quodeq.analysis.subagents.verify.partition_findings_by_fingerprint")
    @patch("quodeq.analysis.fingerprint.find_previous_fingerprint", return_value=(None, None))
    @patch("quodeq.services.dismissed.dismissed_keys", return_value=set())
    @patch("quodeq.analysis.subagents.verify.load_previous_findings_for_dimension")
    def test_no_prev_fingerprint_looks_it_up(self, mock_load, mock_dk, mock_find_fp, mock_partition, mock_write_cf, mock_group, mock_write_m, mock_pool, tmp_path):
        from quodeq.analysis.subagents._verification import _run_verification_step
        mock_load.return_value = [{"file": "a.py", "p": "", "line": 0}]
        mock_partition.return_value = ([], [{"file": "a.py"}])
        config = RunConfig(src=tmp_path, language="python")
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        _run_verification_step(config, "security", evidence_dir, ["a.py"], prev_fingerprint=None)
        mock_find_fp.assert_called_once_with(evidence_dir, "security")
