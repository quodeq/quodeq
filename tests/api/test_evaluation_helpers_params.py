"""Tests for maxSubagents/timeLimit/contextSize validation (finding 5880).

_coerce_int used to swallow any TypeError/ValueError and silently return the
default, so a client sending e.g. ``maxSubagents: "abc"`` got the default
value with no error at all. It must now raise, naming the field, for a
present-but-malformed value, while a genuinely absent value still defaults.
"""
from __future__ import annotations

import pytest

from quodeq.api._evaluation_helpers import _build_evaluation_options, _coerce_int
from quodeq.services.base import DEFAULT_MAX_SUBAGENTS, DEFAULT_TIME_LIMIT


class TestCoerceInt:
    def test_missing_value_returns_default(self):
        assert _coerce_int(None, 5, "maxSubagents") == 5

    def test_convertible_value_converts(self):
        assert _coerce_int("7", 5, "maxSubagents") == 7

    def test_malformed_value_raises_naming_the_field(self):
        with pytest.raises(ValueError, match="maxSubagents"):
            _coerce_int("abc", 5, "maxSubagents")

    def test_malformed_value_names_what_was_received(self):
        with pytest.raises(ValueError, match=r"got 'abc'"):
            _coerce_int("abc", 5, "maxSubagents")


class TestBuildEvaluationOptionsIntFields:
    @staticmethod
    def _payload(**overrides):
        return {"repo": "x", **overrides}

    def test_absent_max_subagents_keeps_default(self):
        options = _build_evaluation_options(self._payload())
        assert options.max_subagents == DEFAULT_MAX_SUBAGENTS

    def test_malformed_max_subagents_raises_400_worthy_error(self):
        with pytest.raises(ValueError, match="maxSubagents"):
            _build_evaluation_options(self._payload(maxSubagents="abc"))

    def test_absent_time_limit_keeps_default(self):
        options = _build_evaluation_options(self._payload())
        assert options.time_limit == DEFAULT_TIME_LIMIT

    def test_malformed_time_limit_raises_400_worthy_error(self):
        with pytest.raises(ValueError, match="timeLimit"):
            _build_evaluation_options(self._payload(timeLimit="abc"))

    def test_absent_context_size_keeps_default(self):
        options = _build_evaluation_options(self._payload())
        assert options.context_size == 0

    def test_malformed_context_size_raises_400_worthy_error(self):
        with pytest.raises(ValueError, match="contextSize"):
            _build_evaluation_options(self._payload(contextSize="abc"))
