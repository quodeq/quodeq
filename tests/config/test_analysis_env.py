"""Accessors in config/analysis_env.py own the raw env read/parse only;
the business rules (clamping, fallbacks, scaling) stay with the callers."""
from __future__ import annotations

import pytest

from quodeq.config.analysis_env import (
    api_read_timeout_override,
    context_size_override,
    max_output_tokens_override,
)


@pytest.mark.parametrize("accessor, var", [
    (max_output_tokens_override, "QUODEQ_MAX_OUTPUT_TOKENS"),
    (api_read_timeout_override, "QUODEQ_API_READ_TIMEOUT"),
    (context_size_override, "QUODEQ_CONTEXT_SIZE"),
])
class TestDigitParseOverrides:
    def test_unset_reads_as_none(self, accessor, var):
        assert accessor({}) is None

    def test_digits_parse(self, accessor, var):
        assert accessor({var: "123"}) == 123

    def test_zero_parses_as_zero_not_none(self, accessor, var):
        # 0 is a real value ("disable") — the caller owns what it means.
        assert accessor({var: "0"}) == 0

    def test_whitespace_is_stripped(self, accessor, var):
        assert accessor({var: " 42 "}) == 42

    @pytest.mark.parametrize("raw", ["", "  ", "-5", "12.5", "soon"])
    def test_non_digit_reads_as_unset(self, accessor, var, raw):
        assert accessor({var: raw}) is None

    def test_os_environ_fallback(self, accessor, var, monkeypatch):
        monkeypatch.setenv(var, "7")
        assert accessor() == 7
