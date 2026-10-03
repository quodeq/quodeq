"""Tests for maxSubagents/timeLimit/contextSize validation.

coerce_int used to swallow any TypeError/ValueError and silently return the
default, so a client sending e.g. ``maxSubagents: "abc"`` got the default
value with no error at all. It must now raise, naming the field, for a
present-but-malformed value, while a genuinely absent value still defaults.
"""
from __future__ import annotations

from http import HTTPStatus
from unittest.mock import patch

import pytest

from quodeq.api._evaluation_helpers import InvalidEvaluationOption, coerce_int
from quodeq.api._evaluation_options import (
    build_evaluation_options,
    _parse_flags,
    _parse_limits,
)
from quodeq.services.base import DEFAULT_MAX_SUBAGENTS, DEFAULT_TIME_LIMIT


class TestCoerceInt:
    def test_missing_value_returns_default(self):
        assert coerce_int(None, 5, "maxSubagents") == 5

    def test_convertible_value_converts(self):
        assert coerce_int("7", 5, "maxSubagents") == 7

    def test_malformed_value_raises_naming_the_field(self):
        with pytest.raises(ValueError, match="maxSubagents"):
            coerce_int("abc", 5, "maxSubagents")

    def test_malformed_value_is_not_echoed_back(self):
        """The message names the field and nothing else. Echoing the received
        value put request input into the response body (CodeQL alert 301,
        reflected XSS pattern); harmless under nosniff+CSP, but the API-wide
        invariant is that no request input is ever reflected back."""
        with pytest.raises(ValueError) as excinfo:
            coerce_int("abc", 5, "maxSubagents")
        assert "abc" not in str(excinfo.value)

    def test_blank_value_is_treated_as_absent(self):
        assert coerce_int("", 5, "maxSubagents") == 5

    def test_whitespace_only_value_is_treated_as_absent(self):
        assert coerce_int("  ", 5, "maxSubagents") == 5


class TestBuildEvaluationOptionsIntFields:
    @staticmethod
    def _payload(**overrides):
        return {"repo": "x", **overrides}

    def test_absent_max_subagents_keeps_default(self):
        options = build_evaluation_options(self._payload())
        assert options.max_subagents == DEFAULT_MAX_SUBAGENTS

    def test_malformed_max_subagents_raises_400_worthy_error(self):
        with pytest.raises(ValueError, match="maxSubagents"):
            build_evaluation_options(self._payload(maxSubagents="abc"))

    def test_absent_time_limit_keeps_default(self):
        options = build_evaluation_options(self._payload())
        assert options.time_limit == DEFAULT_TIME_LIMIT

    def test_malformed_time_limit_raises_400_worthy_error(self):
        with pytest.raises(ValueError, match="timeLimit"):
            build_evaluation_options(self._payload(timeLimit="abc"))

    def test_absent_context_size_keeps_default(self):
        options = build_evaluation_options(self._payload())
        assert options.context_size == 0

    def test_malformed_context_size_raises_400_worthy_error(self):
        with pytest.raises(ValueError, match="contextSize"):
            build_evaluation_options(self._payload(contextSize="abc"))

    def test_malformed_legacy_pool_budget_names_pool_budget(self):
        """The label is the key the client actually sent: reporting the
        legacy poolBudget as timeLimit named a field absent from the body."""
        with pytest.raises(ValueError, match="poolBudget"):
            build_evaluation_options(self._payload(poolBudget="abc"))

    def test_malformed_time_limit_still_names_time_limit_when_both_are_sent(self):
        with pytest.raises(ValueError, match="timeLimit"):
            build_evaluation_options(self._payload(timeLimit="abc", poolBudget=600))

    def test_blank_time_limit_keeps_the_default(self):
        options = build_evaluation_options(self._payload(timeLimit=""))
        assert options.time_limit == DEFAULT_TIME_LIMIT


class TestPostEvaluationsMalformedOption:
    """End to end: the field-naming message must reach the client instead
    of the route's generic "Invalid evaluation options" catch-all."""

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


class TestParseLimits:
    """The numeric half of the option split: clamping and legacy keys."""

    def test_defaults_when_absent(self):
        limits = _parse_limits({})
        assert limits.max_subagents == DEFAULT_MAX_SUBAGENTS
        assert limits.time_limit == DEFAULT_TIME_LIMIT

    def test_clamps_subagents_to_range(self):
        assert _parse_limits({"maxSubagents": 99}).max_subagents == 10
        assert _parse_limits({"maxSubagents": 0}).max_subagents == 1

    def test_zero_time_limit_is_preserved_not_clamped(self):
        assert _parse_limits({"timeLimit": 0}).time_limit == 0

    def test_clamps_time_limit_to_range(self):
        assert _parse_limits({"timeLimit": 5}).time_limit == 60
        assert _parse_limits({"timeLimit": 99999}).time_limit == 3600

    def test_legacy_pool_budget_is_used_when_time_limit_absent(self):
        assert _parse_limits({"poolBudget": 120}).time_limit == 120

    def test_malformed_legacy_value_names_the_key_the_client_sent(self):
        with pytest.raises(InvalidEvaluationOption, match="poolBudget"):
            _parse_limits({"poolBudget": "abc"})


class TestParseFlags:
    """The non-numeric half: models, scope and provider credentials."""

    def test_subagent_model_defaults_to_orchestrator_model(self):
        flags = _parse_flags({"aiModel": "opus"})
        assert flags.subagent_model == "opus"

    def test_explicit_subagent_model_wins(self):
        flags = _parse_flags({"aiModel": "opus", "subagentModel": "haiku"})
        assert flags.subagent_model == "haiku"

    def test_blank_fields_become_none(self):
        flags = _parse_flags({"aiCmd": "", "aiModel": "", "scopePath": ""})
        assert flags.ai_cmd is None
        assert flags.ai_model is None
        assert flags.scope_path is None

    def test_invalid_scope_path_raises(self):
        with pytest.raises(ValueError):
            _parse_flags({"scopePath": "../escape"})

    def test_payload_api_key_is_used_without_the_store_lookup(self):
        with patch("quodeq.api._evaluation_options.get_api_key_secure") as mock:
            flags = _parse_flags({"aiCmd": "claude", "apiKey": "sk-payload"})
        assert flags.provider_api_key == "sk-payload"
        mock.assert_not_called()
