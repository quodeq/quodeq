"""The projects-list summary read must never compute inline.

Regression context: the list path used to run the full accumulated recompute
per project on a cache miss, blocking first paint for minutes after an
upgrade. Misses now report pending; the warm-up engine fills the cache.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.data.fs.report_parser._run_info import RunInfo
from quodeq.services._fs_metadata import _compute_summary, _read_accumulated_summary, warm_project_summary


def _project(tmp_path: Path, name: str = "proj") -> Path:
    d = tmp_path / name
    d.mkdir()
    return d


def _runs() -> list[RunInfo]:
    return [RunInfo(run_id="r1", date_iso="2026-08-01", date_label="1 Aug", status="complete")]


def _cancelled_runs() -> list[RunInfo]:
    return [RunInfo(run_id="r1", date_iso="2026-08-01", date_label="1 Aug", status="cancelled")]


def test_miss_returns_pending_without_computing(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    _project(tmp_path)
    with patch("quodeq.services._fs_metadata._compute_summary") as compute:
        grade, score, files, pending = _read_accumulated_summary(
            tmp_path, "proj", _runs(), DEFAULT_PARAMS)
    compute.assert_not_called()
    assert (grade, score, files, pending) == (None, None, None, True)


def test_no_complete_runs_is_not_pending(tmp_path, monkeypatch):
    """A project with NO runs at all can never be warmed (warm_project_summary
    also requires at least one run), so it must never report pending -- there
    is nothing the warm-up engine will ever fill in."""
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    _project(tmp_path)
    with patch("quodeq.services._fs_metadata._compute_summary") as compute:
        grade, score, files, pending = _read_accumulated_summary(
            tmp_path, "proj", [], DEFAULT_PARAMS)
    compute.assert_not_called()
    assert (grade, score, files, pending) == (None, None, None, False)


def test_cancelled_only_miss_returns_pending_without_computing(tmp_path, monkeypatch):
    """Runs exist (cancelled-only, no complete run) but nothing is cached
    yet: the read-only path must report pending, not silently settle to
    None -- warm_project_summary WILL compute a fallback grade for this
    project (see test_warm_cancelled_only_then_read_hits_without_pending),
    so reporting it settled here would make the grade disappear forever."""
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    _project(tmp_path)
    with patch("quodeq.services._fs_metadata._compute_summary") as compute:
        grade, score, files, pending = _read_accumulated_summary(
            tmp_path, "proj", _cancelled_runs(), DEFAULT_PARAMS)
    compute.assert_not_called()
    assert (grade, score, files, pending) == (None, None, None, True)


def test_warm_cancelled_only_then_read_hits_without_pending(tmp_path, monkeypatch):
    """warm_project_summary must compute a fallback grade for a project whose
    only runs are cancelled (select_default_view_runs' cancelled fallback) --
    it must NOT gate on any run being "complete", or such a project could
    never regain a grade on the repositories screen."""
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    _project(tmp_path)
    with patch(
        "quodeq.services._fs_metadata._compute_summary",
        return_value={"grade": "D", "score": 4.0, "files": 2},
    ) as compute, patch(
        "quodeq.data.fs.report_parser.runs.list_runs", return_value=_cancelled_runs(),
    ):
        warm_project_summary(tmp_path, "proj")
        assert compute.call_count == 1
        grade, score, files, pending = _read_accumulated_summary(
            tmp_path, "proj", _cancelled_runs(), DEFAULT_PARAMS)
    assert (grade, score, files, pending) == ("D", 4.0, 2, False)
    assert compute.call_count == 1  # the read did not recompute


def test_warm_then_read_hits_without_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    _project(tmp_path)
    with patch(
        "quodeq.services._fs_metadata._compute_summary",
        return_value={"grade": "B", "score": 7.5, "files": 10},
    ) as compute, patch(
        "quodeq.data.fs.report_parser.runs.list_runs", return_value=_runs(),
    ):
        warm_project_summary(tmp_path, "proj")
        assert compute.call_count == 1
        grade, score, files, pending = _read_accumulated_summary(
            tmp_path, "proj", _runs(), DEFAULT_PARAMS)
    assert (grade, score, files, pending) == ("B", 7.5, 10, False)
    assert compute.call_count == 1  # the read did not recompute


def test_compute_on_miss_keeps_inline_behavior_for_shared_path(tmp_path, monkeypatch):
    """The shared-repo route has no warm-up engine; its list path must keep
    computing summaries inline on a miss, exactly as before."""
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    _project(tmp_path)
    with patch(
        "quodeq.services._fs_metadata._compute_summary",
        return_value={"grade": "C", "score": 5.0, "files": 4},
    ) as compute:
        grade, score, files, pending = _read_accumulated_summary(
            tmp_path, "proj", _runs(), DEFAULT_PARAMS, compute_on_miss=True)
    compute.assert_called_once()
    assert (grade, score, files, pending) == ("C", 5.0, 4, False)


def test_kill_switch_keeps_inline_compute(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
    _project(tmp_path)
    with patch(
        "quodeq.services._fs_metadata._compute_summary",
        return_value={"grade": "A", "score": 9.0, "files": 3},
    ):
        grade, score, files, pending = _read_accumulated_summary(
            tmp_path, "proj", _runs(), DEFAULT_PARAMS)
    assert (grade, score, files, pending) == ("A", 9.0, 3, False)


def test_metadata_read_failure_is_logged(caplog, tmp_path):
    """A malformed/unreadable run/triage file must not fail silently: the
    card falls back to an empty summary, but an operator needs a trace to
    diagnose which project's data is broken."""
    with patch(
        "quodeq.services._fs_metadata._select_accumulated_dims",
        side_effect=json.JSONDecodeError("Expecting value", "doc", 0),
    ), caplog.at_level(logging.WARNING):
        result = _compute_summary(tmp_path, "proj", [], DEFAULT_PARAMS, set())
    assert result == {"grade": None, "score": None, "files": None}
    assert any(
        "metadata" in r.message.lower() or "triage" in r.message.lower()
        for r in caplog.records
    )
