import logging

from quodeq.shared.logging import log_info, log_debug, _logger


def test_log_info_format(capsys):
    log_info("hello")
    captured = capsys.readouterr()
    assert "[INFO]" in captured.err
    assert "hello" in captured.err


def test_log_debug_format(capsys):
    original_level = _logger.level
    _logger.setLevel(logging.DEBUG)
    try:
        log_debug("test")
        captured = capsys.readouterr()
        assert "[DEBUG]" in captured.err
        assert "test" in captured.err
    finally:
        _logger.setLevel(original_level)


def test_a_logged_exception_carries_its_traceback_to_stderr(capsys):
    try:
        raise ValueError("inner")
    except ValueError:
        logging.getLogger("quodeq.tests").warning("outer", exc_info=True)
    err = capsys.readouterr().err
    assert "outer\nTraceback (most recent call last)" in err
    assert "ValueError: inner" in err


def test_a_logged_stack_reaches_stderr(capsys):
    logging.getLogger("quodeq.tests").warning("where", stack_info=True)
    assert "where\nStack (most recent call last)" in capsys.readouterr().err
