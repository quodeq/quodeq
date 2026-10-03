"""env_int(warn=False): the same fallbacks as env_int, without the warning."""
from __future__ import annotations

import logging

import pytest

from quodeq.shared.env import env_int


@pytest.mark.parametrize("raw", ["", "abc", "0", "-3"])
def test_quiet_read_falls_back_silently(raw: str, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="quodeq.shared.env"):
        assert env_int("X", 7, minimum=1, env={"X": raw}, warn=False) == 7
    assert caplog.text == ""


def test_quiet_read_returns_a_valid_value() -> None:
    assert env_int("X", 7, minimum=1, env={"X": "12"}, warn=False) == 12


def test_quiet_read_without_minimum_keeps_zero_and_negatives() -> None:
    assert env_int("X", 7, env={"X": "0"}, warn=False) == 0
    assert env_int("X", 7, env={"X": "-2"}, warn=False) == -2


def test_default_read_still_warns(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="quodeq.shared.env"):
        assert env_int("X", 7, minimum=1, env={"X": "0"}) == 7
    assert "Out-of-range X=" in caplog.text
