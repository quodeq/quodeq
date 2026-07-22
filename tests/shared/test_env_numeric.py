"""Tests for the shared env_int/env_float defensive parsers."""
import logging

from quodeq.shared._env import env_float, env_int


class TestEnvInt:
    def test_valid_value(self):
        assert env_int("X", 5, env={"X": "42"}) == 42

    def test_missing_returns_default(self):
        assert env_int("X", 5, env={}) == 5

    def test_invalid_returns_default_and_warns(self, caplog):
        with caplog.at_level(logging.WARNING, logger="quodeq.shared._env"):
            assert env_int("X", 5, env={"X": "abc"}) == 5
        assert "Invalid X=" in caplog.text

    def test_below_minimum_returns_default(self, caplog):
        with caplog.at_level(logging.WARNING, logger="quodeq.shared._env"):
            assert env_int("X", 5, minimum=1, env={"X": "0"}) == 5
        assert "Out-of-range X=" in caplog.text

    def test_at_minimum_is_accepted(self):
        assert env_int("X", 5, minimum=1, env={"X": "1"}) == 1


class TestEnvFloat:
    def test_valid_value(self):
        assert env_float("X", 1.5, env={"X": "2.5"}) == 2.5

    def test_missing_returns_default(self):
        assert env_float("X", 1.5, env={}) == 1.5

    def test_invalid_returns_default_and_warns(self, caplog):
        with caplog.at_level(logging.WARNING, logger="quodeq.shared._env"):
            assert env_float("X", 1.5, env={"X": "nan-ish"}) == 1.5
        assert "Invalid X=" in caplog.text

    def test_below_minimum_returns_default(self):
        assert env_float("X", 1.5, minimum=0.0, env={"X": "-3"}) == 1.5
