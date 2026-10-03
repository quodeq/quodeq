"""Exception base for errors whose message is safe to show a client."""
from __future__ import annotations

# Error codes a service-layer outcome carries to the client. They live here,
# not in quodeq.api._constants (which re-exports them), because services may
# not import api.
CODE_PROJECT_EXISTS = "PROJECT_EXISTS"  # 409 for a project already registered or imported
# The optional "action" field (copy|replace) on an import or pull collision.
CODE_INVALID_ACTION = "INVALID_ACTION"


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
