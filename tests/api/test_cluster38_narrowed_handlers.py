"""Custom logging handlers contain their own failures (stdlib handleError contract)."""
from __future__ import annotations

import logging
from unittest.mock import patch

from quodeq.api import _log_buffer, security as security_module
from quodeq.shared.log_throttle import LogThrottle


def _bad_record() -> logging.LogRecord:
    # "%d" with a non-numeric arg makes Formatter.format raise TypeError.
    return logging.LogRecord("t", logging.INFO, __file__, 1, "%d items", ("not-a-number",), None)


def test_buffer_handler_routes_format_failure_to_handle_error() -> None:
    handler = _log_buffer._BufferHandler(_log_buffer.LogBuffer(max_lines=10))
    record = _bad_record()
    with patch.object(handler, "handleError") as handle_error:
        handler.emit(record)  # must not raise
    handle_error.assert_called_once_with(record)


def test_buffer_handler_still_appends_well_formed_records() -> None:
    buffer = _log_buffer.LogBuffer(max_lines=10)
    handler = _log_buffer._BufferHandler(buffer)
    handler.emit(logging.LogRecord("t", logging.INFO, __file__, 1, "%d items", (3,), None))
    assert any("3 items" in str(entry) for entry in buffer._entries)


def test_csp_failure_logger_is_called_directly() -> None:
    throttle = LogThrottle(security_module._CSP_WS_FAILURE_LOG_INTERVAL_S)
    with patch.object(security_module._logger, "warning") as warning:
        security_module._log_csp_ws_failure(ValueError("boom"), throttle)
    warning.assert_called_once()
    assert "ValueError" in warning.call_args.args
