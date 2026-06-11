"""Per-run aggregate drop-ratio metric for the API runner (issue #606).

Dropped-finding counts are surfaced per call as WARNING lines in
``_api_runner``; a systemic parsing problem (a prompt or model change that
makes the model emit a malformed finding shape across many files) is
invisible without eyeballing thousands of per-call lines. The
``_drop_stats`` accumulator aggregates per-call (dropped, kept) counts
across the run; the dimension loops report the aggregate once at end of
run, elevate a single warning when the drop ratio crosses the threshold,
and emit a structured ``drop_stats`` marker for the dashboard stream.
"""
from __future__ import annotations

import json
import logging

import pytest

from quodeq.analysis import _drop_stats


@pytest.fixture(autouse=True)
def _reset_accumulator():
    _drop_stats.consume()
    yield
    _drop_stats.consume()


@pytest.fixture(autouse=True)
def _propagate_quodeq_logs():
    # The quodeq logger has propagate=False (StderrHandler only); flip it so
    # pytest's caplog handler (on the root logger) receives the records.
    qlog = logging.getLogger("quodeq")
    orig = qlog.propagate
    qlog.propagate = True
    yield
    qlog.propagate = orig


class TestAccumulator:
    def test_record_accumulates_and_consume_resets(self):
        _drop_stats.record(dropped=2, kept=8)
        _drop_stats.record(dropped=1, kept=9)
        stats = _drop_stats.consume()
        assert stats.dropped == 3
        assert stats.kept == 17
        assert stats.parsed == 20
        assert stats.ratio == pytest.approx(0.15)
        # consume() resets: the next consume sees a fresh accumulator.
        assert _drop_stats.consume().parsed == 0

    def test_ratio_is_zero_when_nothing_parsed(self):
        assert _drop_stats.DropStats().ratio == 0.0


class TestReport:
    def test_silent_when_no_api_calls_recorded(self, caplog, capsys):
        """CLI-provider runs (no API calls) must not gain a noise line or a
        spurious marker."""
        with caplog.at_level(logging.INFO):
            stats = _drop_stats.report_run_drop_stats()
        assert stats.parsed == 0
        assert caplog.records == []
        assert capsys.readouterr().out == ""

    def test_logs_summary_below_threshold_without_warning(self, caplog):
        _drop_stats.record(dropped=1, kept=99)  # 1% < 5% threshold
        with caplog.at_level(logging.INFO):
            _drop_stats.report_run_drop_stats()
        infos = [r for r in caplog.records if r.levelno == logging.INFO]
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(infos) == 1
        assert "dropped 1 of 100" in infos[0].getMessage()
        assert warnings == []

    def test_elevates_single_warning_above_threshold(self, caplog):
        _drop_stats.record(dropped=2, kept=8)  # 20% > 5% threshold
        with caplog.at_level(logging.INFO):
            _drop_stats.report_run_drop_stats()
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
        assert "20.0%" in warnings[0].getMessage()

    def test_no_warning_at_exactly_the_threshold(self, caplog):
        """The threshold is strict: 'crosses', not 'reaches'."""
        _drop_stats.record(dropped=1, kept=19)  # exactly 5%
        with caplog.at_level(logging.INFO):
            _drop_stats.report_run_drop_stats()
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warnings == []

    def test_emits_drop_stats_marker(self, capsys):
        """Structured marker for the dashboard / SSE stream, mirroring the
        per-dim ``cache_stats`` marker pattern."""
        _drop_stats.record(dropped=2, kept=8)
        _drop_stats.report_run_drop_stats()
        out = capsys.readouterr().out
        markers = [json.loads(ln) for ln in out.splitlines() if ln.strip()]
        drop_markers = [m for m in markers if m.get("_cc") == "drop_stats"]
        assert len(drop_markers) == 1
        assert drop_markers[0]["dropped"] == 2
        assert drop_markers[0]["kept"] == 8
        assert drop_markers[0]["ratio"] == pytest.approx(0.2)

    def test_report_consumes_the_accumulator(self):
        """One report per run: a second report (or next run in the same
        process) starts from zero."""
        _drop_stats.record(dropped=1, kept=1)
        _drop_stats.report_run_drop_stats()
        assert _drop_stats.consume().parsed == 0
