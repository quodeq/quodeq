"""Log sink abstraction so inner layers never import a logging framework.

``core``, ``analysis``, ``services`` and ``config`` accept an injected
:class:`LogSink` instead of importing ``logging`` (stdlib or
``quodeq.shared.logging``) directly. The default everywhere is
:data:`NULL_LOG`, a silent no-op -- composition roots (CLI, api, dashboard)
pass a real sink, e.g. ``quodeq.shared.log_sink.SHARED_LOG``.
"""
from __future__ import annotations

from typing import Protocol


class LogSink(Protocol):
    """Minimal logging surface injectable into inner layers.

    ``success`` exists alongside the four stdlib-style levels because the
    shared colored-console logger renders success lines distinctly (green);
    collapsing it into ``info`` would lose that on the CLI.
    """

    def info(self, message: str) -> None:
        """Report normal progress an operator watching the run would want."""
        ...

    def warning(self, message: str) -> None:
        """Report something the run recovered from and carried on past."""
        ...

    def debug(self, message: str) -> None:
        """Report diagnostic detail. Sinks are free to drop it entirely."""
        ...

    def error(self, message: str) -> None:
        """Report a failure the caller has already dealt with; this does not raise."""
        ...

    def success(self, message: str) -> None:
        """Report a completed step. Console sinks render these in green."""
        ...


class NullLog:
    """A :class:`LogSink` that discards every message. The safe default."""

    def info(self, message: str) -> None:
        """Discard the message."""
        pass

    def warning(self, message: str) -> None:
        """Discard the message."""
        pass

    def debug(self, message: str) -> None:
        """Discard the message."""
        pass

    def error(self, message: str) -> None:
        """Discard the message. Nothing is recorded, not even failures."""
        pass

    def success(self, message: str) -> None:
        """Discard the message."""
        pass


NULL_LOG: LogSink = NullLog()
