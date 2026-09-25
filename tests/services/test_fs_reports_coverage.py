"""Tests for quodeq.services.fs_reports — report reading helpers."""
from __future__ import annotations

import json
from unittest.mock import patch

from quodeq.services.fs_reports import _enrich_with_coverage, get_dimension_eval


def _write_scan_json(tmp_path, content: str) -> None:
    """Create proj/scan.json under tmp_path with the given raw text."""
    (tmp_path / "proj").mkdir()
    (tmp_path / "proj" / "scan.json").write_text(content)


class TestEnrichWithCoverage:
    def test_no_scan_file(self, tmp_path):
        payload = {"score": 80}
        result = _enrich_with_coverage(str(tmp_path), "proj", payload)
        assert "totalFiles" not in result

    def test_with_scan_file(self, tmp_path):
        _write_scan_json(tmp_path, json.dumps({"total_files": 100}))
        payload = {"score": 80, "filesCount": 50}
        result = _enrich_with_coverage(str(tmp_path), "proj", payload)
        assert result["totalFiles"] == 100
        assert result["analyzedFiles"] == 50

    def test_analyzed_capped_at_total(self, tmp_path):
        _write_scan_json(tmp_path, json.dumps({"total_files": 10}))
        payload = {"filesCount": 50}
        result = _enrich_with_coverage(str(tmp_path), "proj", payload)
        assert result["analyzedFiles"] == 10

    def test_no_files_count(self, tmp_path):
        _write_scan_json(tmp_path, json.dumps({"total_files": 100}))
        payload = {}
        result = _enrich_with_coverage(str(tmp_path), "proj", payload)
        assert result["analyzedFiles"] is None

    def test_corrupt_scan_json(self, tmp_path):
        _write_scan_json(tmp_path, "not json")
        payload = {"score": 80}
        result = _enrich_with_coverage(str(tmp_path), "proj", payload)
        assert "totalFiles" not in result


class TestGetDimensionEval:
    def test_path_traversal(self, tmp_path):
        result = get_dimension_eval(str(tmp_path), "../etc", "run", "dim")
        assert result is None

    def test_run_dir_exists_no_result(self, tmp_path):
        run_dir = tmp_path / "proj" / "run1"
        run_dir.mkdir(parents=True)
        with patch("quodeq.services.fs_reports.resolve_dimension_eval", return_value=None):
            result = get_dimension_eval(str(tmp_path), "proj", "run1", "dim")
            assert result is not None
            assert result.get("waiting") is True

    def test_run_dir_not_exists(self, tmp_path):
        with patch("quodeq.services.fs_reports.resolve_dimension_eval", return_value=None):
            result = get_dimension_eval(str(tmp_path), "proj", "run1", "dim")
            assert result is None

    def test_evaluators_dir_override_reaches_resolve_options(self, tmp_path):
        """An injected *evaluators_dir* is used instead of the global
        ``default_paths().evaluators_dir`` (CLEA-DEP-07, row 10718)."""
        run_dir = tmp_path / "proj" / "run1"
        run_dir.mkdir(parents=True)
        custom_evaluators = tmp_path / "custom-evaluators"
        custom_evaluators.mkdir()
        with patch("quodeq.services.fs_reports.resolve_dimension_eval", return_value=None) as mock_resolve:
            get_dimension_eval(
                str(tmp_path), "proj", "run1", "dim", evaluators_dir=custom_evaluators,
            )
        options = mock_resolve.call_args.kwargs["options"]
        assert options.evaluators_dir == custom_evaluators
