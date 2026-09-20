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


_GETTER_CASES = [
    (get_action_api_port, "QUODEQ_ACTION_API_PORT", lambda: _get_config()["action_api_port"]),
    (get_action_api_host, "QUODEQ_ACTION_API_HOST", lambda: _get_config()["default_host"]),
    (get_dashboard_port, "QUODEQ_DASHBOARD_PORT", lambda: _get_config()["dashboard_port"]),
    (get_anthropic_api_key, "ANTHROPIC_API_KEY", lambda: None),
    (get_asvs_url, "QUODEQ_ASVS_URL", lambda: _get_config()["asvs_url"]),
    (get_github_search_url, "QUODEQ_GITHUB_SEARCH_URL", lambda: _get_config()["github_search_url"]),
    (get_github_raw_base_url, "QUODEQ_GITHUB_RAW_BASE_URL", lambda: _get_config()["github_raw_base_url"]),
]


@pytest.mark.parametrize(
    "getter,env_var,expected_default",
    _GETTER_CASES,
    ids=[case[1] for case in _GETTER_CASES],
)
def test_empty_env_mapping_ignores_process_environment(getter, env_var, expected_default, monkeypatch):
    """An injected `env={}` must win over a real process env var, not fall back to it.

    Sets *env_var* to a value in the real process environment first, then
    proves the getter still returns its default when handed an empty mapping
    -- catches a regression back to `env or os.environ`, which would silently
    read the process value here instead.
    """
    monkeypatch.setenv(env_var, "__process_value_must_be_ignored__")
    assert getter(env={}) == expected_default()
