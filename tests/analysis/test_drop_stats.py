"""Per-run aggregate drop-ratio metric for the API runner (issue #606).

Dropped-finding counts are surfaced per call as WARNING lines in
``_api_runner``; a systemic parsing problem (a prompt or model change that
makes the model emit a malformed finding shape across many files) is
invisible without eyeballing thousands of per-call lines. The
``_drop_stats`` accumulator aggregates per-call (dropped, kept) counts
across the run; the dimension loops report the aggregate once at end of
run and elevate a single warning when the drop ratio crosses the threshold.

``report_run_drop_stats`` takes an injected ``log: LogSink`` (core has no
stdlib logging) rather than a module logger; the dashboard ``drop_stats``
marker is emitted by the caller (``_loops.py``), not here -- see
``tests/analysis/test_loops_drop_stats.py`` for that half.
"""
from __future__ import annotations

import pytest

from quodeq.analysis import _drop_stats
from tests.conftest import RecordingLog


@pytest.fixture(autouse=True)
def _isolated_counter(monkeypatch):
    # The module wrappers delegate to the default counter; swap in a fresh
    # instance so nothing leaks in from (or out to) other tests.
    monkeypatch.setattr(_drop_stats, "_default_counter", _drop_stats.DropStatsCounter())


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

    def test_counter_instances_are_independent(self):
        a, b = _drop_stats.DropStatsCounter(), _drop_stats.DropStatsCounter()
        a.record(dropped=2, kept=8)
        b.record(dropped=1, kept=0)
        assert a.consume() == _drop_stats.DropStats(dropped=2, kept=8)
        assert b.consume() == _drop_stats.DropStats(dropped=1, kept=0)

    def test_report_accepts_an_explicit_counter(self):
        counter = _drop_stats.DropStatsCounter()
        counter.record(dropped=1, kept=9)
        log = RecordingLog()
        stats = _drop_stats.report_run_drop_stats(counter, log=log)
        assert stats.dropped == 1 and stats.kept == 9
        assert any("dropped 1 of 10" in m for m in log.info_messages)
        # The explicit counter was consumed; the default stayed untouched.
        assert counter.consume().parsed == 0
        assert _drop_stats.consume().parsed == 0


class TestReport:
    def test_silent_when_no_api_calls_recorded(self):
        """CLI-provider runs (no API calls) must not gain a noise line."""
        log = RecordingLog()
        stats = _drop_stats.report_run_drop_stats(log=log)
        assert stats.parsed == 0
        assert log.info_messages == []
        assert log.warning_messages == []

    def test_logs_summary_below_threshold_without_warning(self):
        _drop_stats.record(dropped=1, kept=99)  # 1% < 5% threshold
        log = RecordingLog()
        _drop_stats.report_run_drop_stats(log=log)
        assert len(log.info_messages) == 1
        assert "dropped 1 of 100" in log.info_messages[0]
        assert log.warning_messages == []

    def test_elevates_single_warning_above_threshold(self):
        _drop_stats.record(dropped=2, kept=8)  # 20% > 5% threshold
        log = RecordingLog()
        _drop_stats.report_run_drop_stats(log=log)
        assert len(log.warning_messages) == 1
        assert "20.0%" in log.warning_messages[0]

    def test_no_warning_at_exactly_the_threshold(self):
        """The threshold is strict: 'crosses', not 'reaches'."""
        _drop_stats.record(dropped=1, kept=19)  # exactly 5%
        log = RecordingLog()
        _drop_stats.report_run_drop_stats(log=log)
        assert log.warning_messages == []

    def test_no_log_when_default_sink_used(self, capsys):
        """Default ``log`` is the silent NULL_LOG -- production callers that
        forget to inject the shared sink get no output, not a crash."""
        _drop_stats.record(dropped=2, kept=8)
        stats = _drop_stats.report_run_drop_stats()
        assert stats.dropped == 2
        assert capsys.readouterr().out == ""

    def test_report_consumes_the_accumulator(self):
        """One report per run: a second report (or next run in the same
        process) starts from zero."""
        _drop_stats.record(dropped=1, kept=1)
        _drop_stats.report_run_drop_stats()
        assert _drop_stats.consume().parsed == 0
