"""Tests for _fs_metadata.py — _read_accumulated_summary core behavior.

Split from test_fs_metadata.py: grade/score computation, empty/error
cases. Visibility-selection behavior, the default-view-runs card
selection, and per-dimension source-run rescoring are split further into
test_fs_metadata_accumulated_visibility.py, _accumulated_card.py, and
_accumulated_rescore.py to stay under the file-size cap.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.services._fs_metadata import _read_accumulated_summary


class TestReadAccumulatedSummary:
    @patch("quodeq.services._fs_metadata.read_run_data")
    @patch("quodeq.services._fs_metadata.summarize_dimensions")
    def test_computes_summary(self, mock_summarize, mock_read):
        from quodeq.core.types import DimensionResult
        from quodeq.data.fs.report_parser.runs import RunInfo

        dim = DimensionResult(dimension="security", overall_score="8.5/10",
                              overall_grade="A", files_read=10, source_file_count=10)
        mock_read.return_value = [dim]
        mock_summary = type("S", (), {"overall_grade": "A", "numeric_average": 8.5})()
        mock_summarize.return_value = mock_summary

        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        grade, score, files, _pending = _read_accumulated_summary(
            Path("/r"), "proj", runs, compute_on_miss=True)
        assert grade == "A"
        assert score == 8.5
        assert files == 10

    @patch("quodeq.services._fs_metadata.read_run_data", return_value=[])
    def test_no_dimensions(self, mock_read):
        from quodeq.data.fs.report_parser.runs import RunInfo
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        grade, score, files, _pending = _read_accumulated_summary(
            Path("/r"), "proj", runs, compute_on_miss=True)
        assert grade is None
        assert score is None

    def test_empty_runs(self):
        grade, score, files, pending = _read_accumulated_summary(Path("/r"), "proj", [])
        assert grade is None
        assert score is None
        assert files is None
        assert pending is False

    @patch("quodeq.services._fs_metadata.read_run_data", side_effect=OSError("boom"))
    def test_error_returns_none_tuple(self, mock_read):
        from quodeq.data.fs.report_parser.runs import RunInfo
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        grade, score, files, _pending = _read_accumulated_summary(
            Path("/r"), "proj", runs, compute_on_miss=True)
        assert grade is None
        assert score is None
        assert files is None

    @patch("quodeq.services._fs_metadata.read_run_data", side_effect=KeyError("bad file"))
    def test_keyerror_from_read_path_still_means_no_data(self, mock_read):
        """A malformed run file (adapter KeyError) keeps the 'no data' card."""
        from quodeq.data.fs.report_parser.runs import RunInfo
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        grade, score, files, _pending = _read_accumulated_summary(
            Path("/r"), "proj", runs, compute_on_miss=True)
        assert grade is None
        assert score is None
        assert files is None

    def test_keyerror_from_rescore_propagates_not_masked_as_no_data(self, monkeypatch):
        """A KeyError bug inside the rescoring business rule must surface.

        Historically one except clause wrapped both the file reads and the
        ``_rescore_dimension`` call, so a rescoring bug silently became
        {"grade": None} — indistinguishable from a genuinely missing file.
        """
        from quodeq.core.scoring.params import DEFAULT_PARAMS
        from quodeq.core.types import DimensionResult
        from quodeq.data.fs.report_parser.runs import RunInfo
        from quodeq.services._fs_metadata import _compute_summary

        dim = DimensionResult(dimension="security", overall_score="8.5/10",
                              overall_grade="A", files_read=10, source_file_count=10)
        monkeypatch.setattr("quodeq.services._fs_metadata.read_run_data",
                            lambda *a, **kw: [dim])
        monkeypatch.setattr("quodeq.services.dismissed.dismissed_keys",
                            lambda project_dir: {("REQ-1", "P", "f.py", 1)})
        monkeypatch.setattr("quodeq.services.deleted.deleted_keys",
                            lambda project_dir: set())

        def buggy_rescore(*a, **kw):
            raise KeyError("rescore bug")

        monkeypatch.setattr("quodeq.services.rescore._rescore_dimension", buggy_rescore)
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        with pytest.raises(KeyError, match="rescore bug"):
            _compute_summary(Path("/r"), "proj", runs, DEFAULT_PARAMS, {"security"})
