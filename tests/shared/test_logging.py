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
