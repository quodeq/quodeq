"""Failed authentication attempts count against the rate limit.

``_check_auth`` used to short-circuit the before_request chain, so a bad
Authorization header was answered 401 forever and never reached the limiter:
unlimited key guessing. A failed auth now records an attempt, whatever the
method or path, and turns into a 429 once the caller is over the cap.
"""
from __future__ import annotations

import pytest

from quodeq.api.app import create_app

_MAX = 3


class _CountingStore:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def check(self, ip: str, now: float) -> bool:
        return self.counts.get(ip, 0) >= _MAX

    def record(self, ip: str, now: float) -> None:
        self.counts[ip] = self.counts.get(ip, 0) + 1

    def check_and_record(self, ip: str, now: float) -> bool:
        if self.check(ip, now):
            return True
        self.record(ip, now)
        return False


@pytest.fixture
def store() -> _CountingStore:
    return _CountingStore()


def _client(tmp_path, monkeypatch, store, api_key):
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path))
    return create_app(rate_limit_store=store, api_key=api_key).test_client()


def test_repeated_bad_key_requests_get_429(tmp_path, monkeypatch, store):
    client = _client(tmp_path, monkeypatch, store, api_key="right-key")
    bad = {"Authorization": "Bearer wrong-key"}
    statuses = [client.get("/api/projects", headers=bad).status_code for _ in range(_MAX + 2)]
    assert statuses[:_MAX] == [401] * _MAX
    assert statuses[-1] == 429


def test_good_key_safe_requests_are_not_counted(tmp_path, monkeypatch, store):
    client = _client(tmp_path, monkeypatch, store, api_key="right-key")
    good = {"Authorization": "Bearer right-key"}
    for _ in range(_MAX + 2):
        assert client.get("/api/projects", headers=good).status_code != 429
    assert store.counts == {}


def test_localhost_without_api_key_is_limited_as_before(tmp_path, monkeypatch, store):
    client = _client(tmp_path, monkeypatch, store, api_key=None)
    for _ in range(_MAX + 2):
        assert client.get("/api/projects").status_code != 429
    assert store.counts == {}
