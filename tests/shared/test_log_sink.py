"""A stdlib Logger is not a LogSink.

``LogSink`` requires ``success`` alongside the four stdlib levels, and
``logging.Logger`` has no such method. ``services/mutation_rescore.py`` was
passing its module logger straight into ``ThreadBackgroundRunner(log=...)``
and ``rescore_run(log=...)``; it only worked because neither callee happened
to call ``.success`` yet. ``LoggerSink`` is the honest adapter for outer-layer
modules that already own a stdlib logger.
"""
from __future__ import annotations

import logging

import pytest

from quodeq.core.observability import LogSink
from quodeq.shared.log_sink import LoggerSink

_METHODS = ("info", "warning", "debug", "error", "success")


def test_logger_sink_exposes_the_full_log_sink_surface():
    sink = LoggerSink(logging.getLogger("test.sink"))
    for name in _METHODS:
        assert callable(getattr(sink, name)), name


@pytest.mark.parametrize(
    ("method", "level"),
    [
        ("debug", logging.DEBUG),
        ("info", logging.INFO),
        ("warning", logging.WARNING),
        ("error", logging.ERROR),
        # No SUCCESS level in stdlib; it is an INFO-level line.
        ("success", logging.INFO),
    ],
)
def test_logger_sink_forwards_each_level_to_the_wrapped_logger(caplog, method, level):
    logger = logging.getLogger("test.sink.levels")
    sink = LoggerSink(logger)
    with caplog.at_level(logging.DEBUG, logger="test.sink.levels"):
        getattr(sink, method)(f"hello from {method}")
    records = [r for r in caplog.records if r.name == "test.sink.levels"]
    assert len(records) == 1
    assert records[0].levelno == level
    assert records[0].getMessage() == f"hello from {method}"


def test_mutation_rescore_hands_its_runner_a_real_sink():
    from quodeq.services import mutation_rescore

    sink = mutation_rescore._log_sink
    for name in _METHODS:
        assert callable(getattr(sink, name)), name
    # The typed contract the callee declares.
    assert isinstance(sink, LoggerSink)
    _typed: LogSink = sink  # noqa: F841 -- assignment is the static check
