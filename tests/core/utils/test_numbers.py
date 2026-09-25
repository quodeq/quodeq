"""clamp keeps a value inside an inclusive range."""
from __future__ import annotations

import pytest

from quodeq.core.utils.numbers import clamp


@pytest.mark.parametrize(("value", "expected"), [(-5, 1), (1, 1), (7, 7), (10, 10), (99, 10)])
def test_clamp(value: int, expected: int) -> None:
    assert clamp(value, 1, 10) == expected
