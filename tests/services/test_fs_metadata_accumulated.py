"""Tests for _fs_metadata.py — read_accumulated_summary core behavior.

Grade/score computation, empty/error cases. Visibility-selection behavior,
the default-view-runs card selection, and per-dimension source-run
rescoring live in test_fs_metadata_accumulated_visibility.py,
_accumulated_card.py, and _accumulated_rescore.py.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.core.types import DimensionResult
from quodeq.data.fs.report_parser.runs import RunInfo
from quodeq.services._fs_metadata import read_accumulated_summary

from tests.services.conftest import stub_row_fetcher

_RUNS = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
_SECURITY = DimensionResult(dimension="security", overall_score="8.5/10",
                            overall_grade="A", files_read=10, source_file_count=10)


class TestReadAccumulatedSummary:
    def test_computes_summary(self, monkeypatch):
        stub_row_fetcher(monkeypatch, lambda root, proj, rid: [_SECURITY])
        grade, score, files, _pending = read_accumulated_summary(
            Path("/r"), "proj", _RUNS, compute_on_miss=True)
        assert (grade, score, files) == ("Good", 8.5, 10)

    def test_no_dimensions(self, monkeypatch):
        stub_row_fetcher(monkeypatch, lambda root, proj, rid: [])
        grade, score, files, _pending = read_accumulated_summary(
            Path("/r"), "proj", _RUNS, compute_on_miss=True)
        assert (grade, score, files) == (None, None, None)

    def test_empty_runs(self):
        grade, score, files, pending = read_accumulated_summary(Path("/r"), "proj", [])
        assert (grade, score, files, pending) == (None, None, None, False)

    @pytest.mark.parametrize("exc", [OSError("boom"), KeyError("bad file")])
    def test_unreadable_triage_means_no_data(self, monkeypatch, exc):
        """An adapter error while loading the project's suppressions keeps the 'no data' card."""
        stub_row_fetcher(monkeypatch, lambda root, proj, rid: [_SECURITY])

        def _broken(project_dir):
            raise exc

        monkeypatch.setattr("quodeq.services.dismissed.dismissed_keys", _broken)
        grade, score, files, _pending = read_accumulated_summary(
            Path("/r"), "proj", _RUNS, compute_on_miss=True)
        assert (grade, score, files) == (None, None, None)

    def test_keyerror_from_summarising_propagates_not_masked_as_no_data(self, monkeypatch):
        """A KeyError bug inside the grading math must surface.

        Historically one except clause wrapped both the file reads and the
        rescore call, so a scoring bug silently became {"grade": None},
        indistinguishable from a genuinely missing file.
        """
        from quodeq.core.scoring.params import DEFAULT_PARAMS
        from quodeq.services._fs_metadata import _compute_summary

        stub_row_fetcher(monkeypatch, lambda root, proj, rid: [_SECURITY])

        def buggy_summarize(*a, **kw):
            raise KeyError("summarise bug")

        monkeypatch.setattr("quodeq.services._fs_metadata.summarize_dimensions", buggy_summarize)
        with pytest.raises(KeyError, match="summarise bug"):
            _compute_summary(Path("/r"), "proj", _RUNS, DEFAULT_PARAMS, {"security"})
