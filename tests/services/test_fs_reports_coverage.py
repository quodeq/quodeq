"""Tests for quodeq.services._fs_reports — report reading helpers."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestEnrichWithCoverage:
    def test_no_scan_file(self, tmp_path):
        from quodeq.services._fs_reports import _enrich_with_coverage
        payload = {"score": 80}
        result = _enrich_with_coverage(str(tmp_path), "proj", payload)
        assert "totalFiles" not in result

    def test_with_scan_file(self, tmp_path):
        from quodeq.services._fs_reports import _enrich_with_coverage
        (tmp_path / "proj").mkdir()
        (tmp_path / "proj" / "scan.json").write_text(json.dumps({"total_files": 100}))
        payload = {"score": 80, "filesCount": 50}
        result = _enrich_with_coverage(str(tmp_path), "proj", payload)
        assert result["totalFiles"] == 100
        assert result["analyzedFiles"] == 50

    def test_analyzed_capped_at_total(self, tmp_path):
        from quodeq.services._fs_reports import _enrich_with_coverage
        (tmp_path / "proj").mkdir()
        (tmp_path / "proj" / "scan.json").write_text(json.dumps({"total_files": 10}))
        payload = {"filesCount": 50}
        result = _enrich_with_coverage(str(tmp_path), "proj", payload)
        assert result["analyzedFiles"] == 10

    def test_no_files_count(self, tmp_path):
        from quodeq.services._fs_reports import _enrich_with_coverage
        (tmp_path / "proj").mkdir()
        (tmp_path / "proj" / "scan.json").write_text(json.dumps({"total_files": 100}))
        payload = {}
        result = _enrich_with_coverage(str(tmp_path), "proj", payload)
        assert result["analyzedFiles"] is None

    def test_corrupt_scan_json(self, tmp_path):
        from quodeq.services._fs_reports import _enrich_with_coverage
        (tmp_path / "proj").mkdir()
        (tmp_path / "proj" / "scan.json").write_text("not json")
        payload = {"score": 80}
        result = _enrich_with_coverage(str(tmp_path), "proj", payload)
        assert "totalFiles" not in result


class TestGetDimensionEval:
    def test_path_traversal(self, tmp_path):
        from quodeq.services._fs_reports import get_dimension_eval
        result = get_dimension_eval(str(tmp_path), "../etc", "run", "dim")
        assert result is None

    def test_run_dir_exists_no_result(self, tmp_path):
        from quodeq.services._fs_reports import get_dimension_eval
        run_dir = tmp_path / "proj" / "run1"
        run_dir.mkdir(parents=True)
        with patch("quodeq.services._fs_reports.resolve_dimension_eval", return_value=None):
            result = get_dimension_eval(str(tmp_path), "proj", "run1", "dim")
            assert result is not None
            assert result.get("waiting") is True

    def test_run_dir_not_exists(self, tmp_path):
        from quodeq.services._fs_reports import get_dimension_eval
        with patch("quodeq.services._fs_reports.resolve_dimension_eval", return_value=None):
            result = get_dimension_eval(str(tmp_path), "proj", "run1", "dim")
            assert result is None
