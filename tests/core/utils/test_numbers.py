"""clamp keeps a value inside an inclusive range; int_or_none never raises."""
from __future__ import annotations

import pytest

from quodeq.core.utils.numbers import clamp, int_or_none


@pytest.mark.parametrize(("value", "expected"), [(-5, 1), (1, 1), (7, 7), (10, 10), (99, 10)])
def test_clamp(value: int, expected: int) -> None:
    assert clamp(value, 1, 10) == expected


@pytest.mark.parametrize(("value", "expected"), [
    (7, 7), ("42", 42), (7.9, 7), (True, 1),
    (None, None), ("x", None), (float("inf"), None), (float("-inf"), None), (float("nan"), None),
])
def test_int_or_none(value: object, expected: int | None) -> None:
    assert int_or_none(value) == expected
