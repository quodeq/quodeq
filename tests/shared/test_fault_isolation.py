"""run_isolated: a fault-isolation boundary that logs the traceback and keeps going."""
from __future__ import annotations

import logging

import pytest

from quodeq.shared.fault_isolation import run_isolated


def _boom() -> int:
    raise ValueError("bad input")


def test_returns_the_result_when_fn_succeeds(recording_log) -> None:
    assert run_isolated(lambda: 7, label="job", log=recording_log) == 7


def test_failure_returns_none_and_logs_the_traceback_to_a_log_sink(recording_log) -> None:
    assert run_isolated(_boom, label="job", log=recording_log) is None
    [message] = recording_log.warning_messages
    assert message.startswith("job failed")
    assert "Traceback (most recent call last)" in message
    assert "ValueError: bad input" in message


def test_failure_uses_exc_info_on_a_stdlib_logger(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("quodeq.test.fault_isolation")
    with caplog.at_level(logging.WARNING, logger=logger.name):
        run_isolated(_boom, label="job", log=logger)
    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert record.getMessage() == "job failed"
    assert record.exc_info is not None and record.exc_info[0] is ValueError


def test_on_error_supplies_the_sentinel(recording_log) -> None:
    seen: list[Exception] = []

    def on_error(exc: Exception) -> int:
        seen.append(exc)
        return -1

    assert run_isolated(_boom, label="job", log=recording_log, on_error=on_error) == -1
    assert isinstance(seen[0], ValueError)


@pytest.mark.parametrize("exc", [KeyboardInterrupt, SystemExit])
def test_base_exceptions_propagate(exc: type[BaseException], recording_log) -> None:
    def fn() -> None:
        raise exc

    with pytest.raises(exc):
        run_isolated(fn, label="job", log=recording_log)
