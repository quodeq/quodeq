"""Small numeric helpers."""
from __future__ import annotations

from typing import TypeVar

_NumT = TypeVar("_NumT", int, float)


def clamp(value: _NumT, low: _NumT, high: _NumT) -> _NumT:
    """Return *value* limited to the inclusive range ``low..high``."""
    return max(low, min(high, value))
