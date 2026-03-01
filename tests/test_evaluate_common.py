from codecompass.evaluate.lib.common import log_error, log_info


def test_log_info_prefix():
    assert log_info("hello") == "  hello"


def test_log_error_prefix():
    assert log_error("boom") == "  ✗ boom"
