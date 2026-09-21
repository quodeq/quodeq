import logging

import pytest

from quodeq.api._log_buffer import LogBuffer

_TEST_MAX_LINES = 3


@pytest.fixture()
def bound_log_buffer():
    """Yield a function that creates a LogBuffer and attaches its handler to
    a named logger. Teardown detaches every handler it attached, even if the
    test body fails an assertion first."""
    created = []

    def _bind(name, level):
        buf = LogBuffer(max_lines=10)
        logger = logging.getLogger(name)
        logger.addHandler(buf.handler)
        logger.setLevel(level)
        created.append((logger, buf.handler))
        return buf, logger

    yield _bind
    for logger, handler in created:
        logger.removeHandler(handler)


def test_append_and_get_lines():
    buf = LogBuffer(max_lines=10)
    buf.append("line one")
    buf.append("line two")
    result = buf.get_lines()
    assert len(result["lines"]) == 2
    assert result["lines"][0]["line"] == "line one"
    assert result["lines"][1]["line"] == "line two"
    assert result["total"] == 2


def test_ring_buffer_overflow():
    buf = LogBuffer(max_lines=_TEST_MAX_LINES)
    for i in range(5):
        buf.append(f"line {i}")
    result = buf.get_lines()
    assert len(result["lines"]) == _TEST_MAX_LINES
    assert result["lines"][0]["line"] == "line 2"
    assert result["lines"][2]["line"] == "line 4"


def test_since_returns_delta():
    buf = LogBuffer(max_lines=10)
    buf.append("old")
    buf.append("new")
    result = buf.get_lines(since=0)
    assert len(result["lines"]) == 1
    assert result["lines"][0]["line"] == "new"
    assert result["lines"][0]["index"] == 1


def test_since_out_of_range_returns_all():
    buf = LogBuffer(max_lines=10)
    buf.append("a")
    buf.append("b")
    result = buf.get_lines(since=99)
    assert len(result["lines"]) == 0


def test_monotonic_index():
    buf = LogBuffer(max_lines=_TEST_MAX_LINES)
    for i in range(5):
        buf.append(f"line {i}")
    result = buf.get_lines()
    indices = [e["index"] for e in result["lines"]]
    assert indices == [2, 3, 4]


def test_handler_captures_log_records(bound_log_buffer):
    buf, logger = bound_log_buffer("test_handler_capture", logging.INFO)
    logger.info("hello from logger")
    result = buf.get_lines()
    assert len(result["lines"]) == 1
    assert "hello from logger" in result["lines"][0]["line"]


def test_clear():
    buf = LogBuffer(max_lines=10)
    buf.append("a")
    buf.append("b")
    buf.clear()
    result = buf.get_lines()
    assert len(result["lines"]) == 0
    assert result["total"] == 0


def test_append_defaults_level_to_info():
    buf = LogBuffer(max_lines=10)
    buf.append("line one")
    result = buf.get_lines()
    assert result["lines"][0]["level"] == "INFO"


def test_append_records_given_level():
    buf = LogBuffer(max_lines=10)
    buf.append("uh oh", level="ERROR")
    result = buf.get_lines()
    assert result["lines"][0]["level"] == "ERROR"


def test_handler_captures_record_level(bound_log_buffer):
    buf, logger = bound_log_buffer("test_handler_capture_level", logging.WARNING)
    logger.warning("uh oh from logger")
    result = buf.get_lines()
    assert len(result["lines"]) == 1
    assert result["lines"][0]["level"] == "WARNING"
