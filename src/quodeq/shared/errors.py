"""Exception base for errors whose message is safe to show a client."""
from __future__ import annotations


class ClientMessageError(Exception):
    """An exception carrying hand-written, client-safe text.

    ``public_message`` is the text a route may return verbatim. Routes read
    that attribute instead of ``str(exc)``, so a response never depends on
    exception formatting and the exception-echo gate
    (tests/api/test_no_exception_echo.py) stays at its zero baseline.

    Lives in ``shared`` rather than ``quodeq.api.helpers`` (which re-exports
    it) because service-layer errors subclass it too, and ``services`` may
    not import ``api``.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_message = message
