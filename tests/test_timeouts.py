"""Tests for the scaled wall-clock budget helper."""
from __future__ import annotations

import pytest

from tests._timeouts import budget, scale


class TestScale:
    def test_defaults_to_one_when_unset(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("QUODEQ_TEST_TIMEOUT_SCALE", raising=False)
        assert scale() == 1.0

    def test_reads_the_env_var(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("QUODEQ_TEST_TIMEOUT_SCALE", "4")
        assert scale() == 4.0

    def test_accepts_a_fractional_value(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("QUODEQ_TEST_TIMEOUT_SCALE", "2.5")
        assert scale() == 2.5

    @pytest.mark.parametrize("raw", ["", "abc", "1,5", "None"])
    def test_unparseable_value_falls_back_to_one(
        self, raw: str, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("QUODEQ_TEST_TIMEOUT_SCALE", raw)
        assert scale() == 1.0

    @pytest.mark.parametrize("raw", ["0", "-3"])
    def test_non_positive_value_falls_back_to_one(
        self, raw: str, monkeypatch: pytest.MonkeyPatch
    ):
        """A zero or negative budget would turn every wait into a no-op."""
        monkeypatch.setenv("QUODEQ_TEST_TIMEOUT_SCALE", raw)
        assert scale() == 1.0


class TestBudget:
    def test_passes_through_unscaled_by_default(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("QUODEQ_TEST_TIMEOUT_SCALE", raising=False)
        assert budget(5) == 5.0

    def test_multiplies_by_the_scale(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("QUODEQ_TEST_TIMEOUT_SCALE", "4")
        assert budget(5) == 20.0

    def test_never_scales_below_the_requested_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """The knob may only buy more headroom, never less."""
        monkeypatch.setenv("QUODEQ_TEST_TIMEOUT_SCALE", "0.5")
        assert budget(5) == 5.0

    def test_reads_the_env_var_at_call_time(self, monkeypatch: pytest.MonkeyPatch):
        """Import order must not freeze the scale."""
        monkeypatch.setenv("QUODEQ_TEST_TIMEOUT_SCALE", "2")
        assert budget(1) == 2.0
        monkeypatch.setenv("QUODEQ_TEST_TIMEOUT_SCALE", "3")
        assert budget(1) == 3.0
