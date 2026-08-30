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
    """Minimal four-level logging surface injectable into inner layers."""

    def info(self, message: str) -> None: ...

    def warning(self, message: str) -> None: ...

    def debug(self, message: str) -> None: ...

    def error(self, message: str) -> None: ...


class NullLog:
    """A :class:`LogSink` that discards every message. The safe default."""

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def debug(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


NULL_LOG: LogSink = NullLog()
