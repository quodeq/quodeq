"""Tests for the assistant session TTL reader's injectable env seam."""
from __future__ import annotations

from quodeq.api._assistant_hygiene import _DEFAULT_SESSION_TTL_DAYS, _session_ttl_days


def test_session_ttl_days_default_with_no_env_arg():
    assert _session_ttl_days({}) == _DEFAULT_SESSION_TTL_DAYS


def test_session_ttl_days_env_override():
    assert _session_ttl_days({"QUODEQ_ASSISTANT_SESSION_TTL_DAYS": "30"}) == 30


def test_session_ttl_days_invalid_value_falls_back_to_default():
    assert _session_ttl_days({"QUODEQ_ASSISTANT_SESSION_TTL_DAYS": "not-a-number"}) == (
        _DEFAULT_SESSION_TTL_DAYS
    )


def test_session_ttl_days_zero_disables():
    assert _session_ttl_days({"QUODEQ_ASSISTANT_SESSION_TTL_DAYS": "0"}) == 0


def test_session_ttl_days_negative_clamped_to_zero():
    assert _session_ttl_days({"QUODEQ_ASSISTANT_SESSION_TTL_DAYS": "-5"}) == 0
