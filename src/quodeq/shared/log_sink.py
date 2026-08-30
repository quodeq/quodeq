"""Production :class:`~quodeq.core.observability.LogSink`.

Delegates to the ``shared.logging`` colored-console helpers, so inner-layer
code that accepts an injected ``log: LogSink`` reaches the same process
logger it used to import directly -- without importing it.
"""
from __future__ import annotations

from quodeq.core.evidence._req_mapping import QuarantinedFinding
from quodeq.core.observability import LogSink
from quodeq.shared.logging import log_debug, log_error, log_info, log_warning


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


SHARED_LOG: LogSink = SharedLog()


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
