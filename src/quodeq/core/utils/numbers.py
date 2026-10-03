"""Small numeric helpers."""
from __future__ import annotations

from typing import TypeVar

_NumT = TypeVar("_NumT", int, float)


def clamp(value: _NumT, low: _NumT, high: _NumT) -> _NumT:
    """Return *value* limited to the inclusive range ``low..high``."""
    return max(low, min(high, value))


def int_or_none(value: object) -> int | None:
    """Return ``int(value)``, or None when that raises.

    Covers ``TypeError`` and ``ValueError`` (junk input) and ``OverflowError``
    (an infinite float, e.g. JSON ``1e400``). Booleans pass through as
    ``int()`` treats them (``True`` -> 1); nothing else is coerced.
    """
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError, OverflowError):
        return None
