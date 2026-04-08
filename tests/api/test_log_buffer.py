import logging

from quodeq.api._log_buffer import LogBuffer


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
    buf = LogBuffer(max_lines=3)
    for i in range(5):
        buf.append(f"line {i}")
    result = buf.get_lines()
    assert len(result["lines"]) == 3
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
    buf = LogBuffer(max_lines=3)
    for i in range(5):
        buf.append(f"line {i}")
    result = buf.get_lines()
    indices = [e["index"] for e in result["lines"]]
    assert indices == [2, 3, 4]


def test_handler_captures_log_records():
    buf = LogBuffer(max_lines=10)
    logger = logging.getLogger("test_handler_capture")
    logger.addHandler(buf.handler)
    logger.setLevel(logging.INFO)
    logger.info("hello from logger")
    result = buf.get_lines()
    assert len(result["lines"]) == 1
    assert "hello from logger" in result["lines"][0]["line"]
    logger.removeHandler(buf.handler)


def test_clear():
    buf = LogBuffer(max_lines=10)
    buf.append("a")
    buf.append("b")
    buf.clear()
    result = buf.get_lines()
    assert len(result["lines"]) == 0
    assert result["total"] == 0
