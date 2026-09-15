"""Cluster 38: RunLogHandler contains writer failures via handleError."""
from __future__ import annotations

import logging
from unittest.mock import patch

from quodeq.shared import run_log


class _FullDisk:
    def write(self, text: str) -> None:
        raise OSError(28, "No space left on device")


def test_run_log_handler_routes_write_failure_to_handle_error() -> None:
    handler = run_log.RunLogHandler(_FullDisk())
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", None, None)
    with patch.object(handler, "handleError") as handle_error:
        handler.emit(record)  # must not raise
    handle_error.assert_called_once_with(record)


def test_run_log_handler_routes_format_failure_to_handle_error() -> None:
    written: list[str] = []

    class _Writer:
        def write(self, text: str) -> None:
            written.append(text)

    handler = run_log.RunLogHandler(_Writer())
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "%d items", ("x",), None)
    with patch.object(handler, "handleError") as handle_error:
        handler.emit(record)
    handle_error.assert_called_once_with(record)
    assert written == []
