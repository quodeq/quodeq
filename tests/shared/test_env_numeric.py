"""Tests for the shared env_int/env_float defensive parsers."""
import logging

import pytest

from quodeq.shared._config import _get_config
from quodeq.shared._env import (
    env_float,
    env_int,
    get_action_api_host,
    get_action_api_port,
    get_anthropic_api_key,
    get_asvs_url,
    get_dashboard_port,
    get_github_raw_base_url,
    get_github_search_url,
)


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


_SENTINEL_PROCESS_VALUE = "__process_value_must_be_ignored__"

_ENV_INT_REGRESSION_VAR = "QUODEQ_ENV_NUMERIC_REGRESSION_INT"
_ENV_FLOAT_REGRESSION_VAR = "QUODEQ_ENV_NUMERIC_REGRESSION_FLOAT"

_GETTER_CASES = [
    (get_action_api_port, "QUODEQ_ACTION_API_PORT", lambda: _get_config()["action_api_port"], _SENTINEL_PROCESS_VALUE),
    (get_action_api_host, "QUODEQ_ACTION_API_HOST", lambda: _get_config()["default_host"], _SENTINEL_PROCESS_VALUE),
    (get_dashboard_port, "QUODEQ_DASHBOARD_PORT", lambda: _get_config()["dashboard_port"], _SENTINEL_PROCESS_VALUE),
    (get_anthropic_api_key, "ANTHROPIC_API_KEY", lambda: None, _SENTINEL_PROCESS_VALUE),
    (get_asvs_url, "QUODEQ_ASVS_URL", lambda: _get_config()["asvs_url"], _SENTINEL_PROCESS_VALUE),
    (get_github_search_url, "QUODEQ_GITHUB_SEARCH_URL", lambda: _get_config()["github_search_url"], _SENTINEL_PROCESS_VALUE),
    (get_github_raw_base_url, "QUODEQ_GITHUB_RAW_BASE_URL", lambda: _get_config()["github_raw_base_url"], _SENTINEL_PROCESS_VALUE),
    # env_int/env_float themselves, called with their real (var, default, env=) signature via
    # a thin lambda. The process value here must be a *valid* number (not a parse-failure
    # sentinel): a non-numeric sentinel would return the default under the old `env or
    # os.environ` bug too (via the except ValueError branch), masking the regression this
    # test exists to catch.
    (
        lambda env: env_int(_ENV_INT_REGRESSION_VAR, 7, env=env),
        _ENV_INT_REGRESSION_VAR,
        lambda: 7,
        "999",
    ),
    (
        lambda env: env_float(_ENV_FLOAT_REGRESSION_VAR, 1.5, env=env),
        _ENV_FLOAT_REGRESSION_VAR,
        lambda: 1.5,
        "999.5",
    ),
]


@pytest.mark.parametrize(
    "getter,env_var,expected_default,process_value",
    _GETTER_CASES,
    ids=[case[1] for case in _GETTER_CASES],
)
def test_empty_env_mapping_ignores_process_environment(getter, env_var, expected_default, process_value, monkeypatch):
    """An injected `env={}` must win over a real process env var, not fall back to it.

    Sets *env_var* to a value in the real process environment first, then
    proves the getter still returns its default when handed an empty mapping
    -- catches a regression back to `env or os.environ`, which would silently
    read the process value here instead.
    """
    monkeypatch.setenv(env_var, process_value)
    assert getter(env={}) == expected_default()
