"""Tests for quodeq.analysis._incremental_phases — phase execution helpers."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestCanCarryForward:
    def test_all_conditions_met(self):
        from quodeq.analysis._incremental_phases import _can_carry_forward
        classification = MagicMock()
        classification.full_reanalysis = False
        classification.unchanged = ["a.py"]
        result = _can_carry_forward({"fp": True}, Path("/prev"), classification)
        assert result is True

    def test_no_prev_fp(self):
        from quodeq.analysis._incremental_phases import _can_carry_forward
        classification = MagicMock()
        classification.full_reanalysis = False
        classification.unchanged = ["a.py"]
        result = _can_carry_forward(None, Path("/prev"), classification)
        assert result is False

    def test_no_prev_evidence(self):
        from quodeq.analysis._incremental_phases import _can_carry_forward
        classification = MagicMock()
        classification.full_reanalysis = False
        classification.unchanged = ["a.py"]
        result = _can_carry_forward({"fp": True}, None, classification)
        assert result is False

    def test_full_reanalysis(self):
        from quodeq.analysis._incremental_phases import _can_carry_forward
        classification = MagicMock()
        classification.full_reanalysis = True
        classification.unchanged = ["a.py"]
        result = _can_carry_forward({"fp": True}, Path("/prev"), classification)
        assert result is False

    def test_no_unchanged(self):
        from quodeq.analysis._incremental_phases import _can_carry_forward
        classification = MagicMock()
        classification.full_reanalysis = False
        classification.unchanged = []
        result = _can_carry_forward({"fp": True}, Path("/prev"), classification)
        assert result is False


class TestMaybeCarryForward:
    def test_carries_forward_when_conditions_met(self, tmp_path):
        from quodeq.analysis._incremental_phases import _maybe_carry_forward
        classification = MagicMock()
        classification.full_reanalysis = False
        classification.unchanged = ["a.py"]
        prev_evidence_dir = tmp_path / "prev"
        prev_evidence_dir.mkdir()
        evidence_dir = tmp_path / "current"
        evidence_dir.mkdir()
        with patch("quodeq.analysis._incremental_phases.carry_forward_findings", return_value=5):
            _maybe_carry_forward({"fp": True}, prev_evidence_dir, classification, "security", evidence_dir)

    def test_skips_when_conditions_not_met(self, tmp_path):
        from quodeq.analysis._incremental_phases import _maybe_carry_forward
        classification = MagicMock()
        classification.full_reanalysis = True
        classification.unchanged = []
        with patch("quodeq.analysis._incremental_phases.carry_forward_findings") as mock_carry:
            _maybe_carry_forward(None, None, classification, "security", tmp_path)
            mock_carry.assert_not_called()


class TestListAllSourceFiles:
    def test_lists_files(self):
        from quodeq.analysis._incremental_phases import _list_all_source_files
        config = MagicMock()
        with patch("quodeq.analysis._incremental_phases._list_source_files", return_value=(["a.py", "b.py"], [".py"])):
            result = _list_all_source_files(config, "security")
            assert result == ["a.py", "b.py"]
