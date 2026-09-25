"""Interface surface between services and data.

Protocols and boundary error types only: this module carries no data-layer
imports. Concretion defaults live in ``services/wiring.py`` — services
import their defaults from there and their types from here, so a storage
swap touches ``wiring`` + ``data/``, never the consumers of this module.
"""
from __future__ import annotations

from quodeq.data.ports.errors import StoreUnreadableError  # noqa: F401
from quodeq.data.ports.grade_tables import GradeTablesReader  # noqa: F401
from quodeq.data.ports.standards_store import StandardsStore  # noqa: F401


class StandardNotFoundError(FileNotFoundError):
    """No custom standard file exists for the requested id.

    Subclasses ``FileNotFoundError`` so existing ``except FileNotFoundError``
    and ``pytest.raises(FileNotFoundError)`` sites keep working; the API
    route catches this domain type instead of the raw OS exception.
    """


class StandardProtectedError(PermissionError):
    """The requested standard is built-in or managed and cannot be written.

    Subclasses ``PermissionError`` for the same reason as
    :class:`StandardNotFoundError`.
    """
