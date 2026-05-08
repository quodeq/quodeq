"""Feature flags — env var parsing."""
from __future__ import annotations

import pytest

from quodeq.analysis.cache.flags import is_cache_v2_enabled, is_result_cache_disabled


@pytest.mark.parametrize("value,expected", [
    ("1", True), ("true", True), ("TRUE", True), ("yes", True), ("on", True),
    ("0", False), ("false", False), ("", False), ("no", False), ("  ", False),
])
def test_v2_flag(monkeypatch, value, expected):
    monkeypatch.setenv("QUODEQ_CACHE_V2", value)
    assert is_cache_v2_enabled() is expected


def test_v2_flag_unset(monkeypatch):
    monkeypatch.delenv("QUODEQ_CACHE_V2", raising=False)
    assert is_cache_v2_enabled() is False


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("QUODEQ_DISABLE_RESULT_CACHE", "1")
    assert is_result_cache_disabled() is True
    monkeypatch.delenv("QUODEQ_DISABLE_RESULT_CACHE", raising=False)
    assert is_result_cache_disabled() is False
