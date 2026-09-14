"""Production :class:`~quodeq.core.observability.LogSink`.

Delegates to the ``shared.logging`` colored-console helpers, so inner-layer
code that accepts an injected ``log: LogSink`` reaches the same process
logger it used to import directly -- without importing it.
"""
from __future__ import annotations

from typing import Protocol

from quodeq.core.evidence import QuarantinedFinding
from quodeq.core.observability import LogSink
from quodeq.shared.logging import log_debug, log_error, log_info, log_success, log_warning


class SharedLog:
    """LogSink that writes through the shared colored-console logger."""

    def info(self, message: str) -> None:
        log_info(message)

    def warning(self, message: str) -> None:
        log_warning(message)

    def debug(self, message: str) -> None:
        log_debug(message)

    def error(self, message: str) -> None:
        log_error(message)

    def success(self, message: str) -> None:
        log_success(message)


SHARED_LOG: LogSink = SharedLog()


class _StdlibLogger(Protocol):
    """The slice of ``logging.Logger`` that ``LoggerSink`` delegates to."""

    def info(self, msg: str) -> None: ...
    def warning(self, msg: str) -> None: ...
    def debug(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...


class LoggerSink:
    """LogSink over a stdlib logger, for outer-layer modules that already own one.

    A ``logging.Logger`` is not a ``LogSink``: it has no ``success``. Passing
    one where a sink is typed only works until the callee uses that level.
    ``success`` maps to INFO here (stdlib has no such level).
    """

    def __init__(self, logger: _StdlibLogger) -> None:
        self._logger = logger

    def info(self, message: str) -> None:
        self._logger.info(message)

    def warning(self, message: str) -> None:
        self._logger.warning(message)

    def debug(self, message: str) -> None:
        self._logger.debug(message)

    def error(self, message: str) -> None:
        self._logger.error(message)

    def success(self, message: str) -> None:
        self._logger.info(message)


def log_quarantined_findings(
    findings: list[QuarantinedFinding], *, log: LogSink = SHARED_LOG,
) -> None:
    """Log each quarantined finding. The message text lives here, once, so
    every parser-entry-point caller that wires ``on_quarantine`` to this
    function gets identical wording instead of re-deriving the format string.
    """
    for f in findings:
        log.warning(
            f"Quarantining unmapped {f.severity or '?'} finding in dimension "
            f"{f.dimension!r}: principle {f.principle!r} not in standard "
            f"(practice_id={f.practice_id!r}, req={f.req!r}, file={f.file})"
        )


def log_malformed_jsonl_line(message: str, *, log: LogSink = SHARED_LOG) -> None:
    """Log a single malformed-JSONL-line message from ``core.evidence._jsonl``."""
    log.warning(message)
