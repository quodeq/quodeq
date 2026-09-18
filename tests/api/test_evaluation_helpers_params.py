"""Tests for maxSubagents/timeLimit/contextSize validation (finding 5880).

_coerce_int used to swallow any TypeError/ValueError and silently return the
default, so a client sending e.g. ``maxSubagents: "abc"`` got the default
value with no error at all. It must now raise, naming the field, for a
present-but-malformed value, while a genuinely absent value still defaults.
"""
from __future__ import annotations

from http import HTTPStatus

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

    def test_blank_value_is_treated_as_absent(self):
        assert _coerce_int("", 5, "maxSubagents") == 5

    def test_whitespace_only_value_is_treated_as_absent(self):
        assert _coerce_int("  ", 5, "maxSubagents") == 5


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

    def test_malformed_legacy_pool_budget_names_pool_budget(self):
        """The label is the key the client actually sent: reporting the
        legacy poolBudget as timeLimit named a field absent from the body."""
        with pytest.raises(ValueError, match="poolBudget"):
            _build_evaluation_options(self._payload(poolBudget="abc"))

    def test_malformed_time_limit_still_names_time_limit_when_both_are_sent(self):
        with pytest.raises(ValueError, match="timeLimit"):
            _build_evaluation_options(self._payload(timeLimit="abc", poolBudget=600))

    def test_blank_time_limit_keeps_the_default(self):
        options = _build_evaluation_options(self._payload(timeLimit=""))
        assert options.time_limit == DEFAULT_TIME_LIMIT


class TestPostEvaluationsMalformedOption:
    """End to end: the field-naming message must reach the client instead
    of the route's generic "Invalid evaluation options" catch-all (review
    round 1 on finding 5880)."""

    @pytest.fixture()
    def client(self, monkeypatch):
        monkeypatch.delenv("QUODEQ_API_KEY", raising=False)
        from quodeq.api.app import create_app
        from tests.api.test_action_api import StubProvider

        return create_app(StubProvider()).test_client()

    def test_malformed_max_subagents_names_the_field_in_the_response(self, client):
        resp = client.post(
            "/api/evaluations",
            json={"repo": "https://github.com/foo/bar", "maxSubagents": "abc"},
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == "INVALID_INPUT"
        assert "maxSubagents" in body["error"]

    def test_absent_max_subagents_starts_normally(self, client):
        resp = client.post(
            "/api/evaluations",
            json={"repo": "https://github.com/foo/bar"},
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == HTTPStatus.ACCEPTED

    def test_blank_max_subagents_starts_normally(self, client):
        """An empty string is how a cleared form field arrives: treat it as
        absent and default, the way it behaved before the validation."""
        resp = client.post(
            "/api/evaluations",
            json={"repo": "https://github.com/foo/bar", "maxSubagents": ""},
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == HTTPStatus.ACCEPTED

    def test_malformed_pool_budget_names_pool_budget_in_the_response(self, client):
        resp = client.post(
            "/api/evaluations",
            json={"repo": "https://github.com/foo/bar", "poolBudget": "abc"},
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == "INVALID_INPUT"
        assert "poolBudget" in body["error"]
