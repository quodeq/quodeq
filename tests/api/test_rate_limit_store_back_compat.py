"""Regression: external RateLimitStore implementers written against the old
check()/record()-only Protocol must keep working.

``InMemoryRateLimitStore``'s docstring advertises that users can implement
``RateLimitStore`` themselves (e.g. a Redis-backed store) and pass it to
``create_app(rate_limit_store=...)``. ``check_and_record`` was added to the
Protocol later; an external implementation written before that addition has
no ``check_and_record`` method, and ``_check_rate_limit`` must fall back to
``check()`` + ``record()`` for it instead of raising ``AttributeError``.
"""
from __future__ import annotations

import pytest

from quodeq.api.app import create_app


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)


class _OldProtocolStore:
    """Duck-typed store implementing only the pre-check_and_record Protocol."""

    def __init__(self, max_requests: int) -> None:
        self._max_requests = max_requests
        self._counts: dict[str, int] = {}

    def check(self, ip: str, now: float) -> bool:
        return self._counts.get(ip, 0) >= self._max_requests

    def record(self, ip: str, now: float) -> None:
        self._counts[ip] = self._counts.get(ip, 0) + 1


def _client(tmp_path, monkeypatch, store):
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path))
    app = create_app(rate_limit_store=store)
    return app.test_client()


def test_old_protocol_store_without_check_and_record_still_enforces_limit(tmp_path, monkeypatch):
    store = _OldProtocolStore(max_requests=3)
    client = _client(tmp_path, monkeypatch, store)

    last_status = None
    for _ in range(6):
        resp = client.post("/api/evaluations", json={}, headers={"Origin": "http://localhost"})
        last_status = resp.status_code
        if last_status == 429:
            break
    assert last_status == 429, (
        f"expected the old check()/record() Protocol to still enforce the cap, got {last_status}"
    )


def test_old_protocol_store_without_check_and_record_allows_under_limit(tmp_path, monkeypatch):
    store = _OldProtocolStore(max_requests=3)
    client = _client(tmp_path, monkeypatch, store)

    resp = client.post("/api/evaluations", json={}, headers={"Origin": "http://localhost"})
    assert resp.status_code != 429


def test_file_store_load_drops_malformed_per_ip_values(tmp_path, monkeypatch):
    """The file backend's state file is user-writable JSON: a per-IP value
    that is not a list of numbers is dropped on load instead of raising on
    every request from that IP."""
    import json

    from quodeq.api.app import create_rate_limit_store

    monkeypatch.setenv("QUODEQ_RATE_LIMIT_MAX", "2")
    path = tmp_path / "rl.json"
    path.write_text(json.dumps({"a": 5, "b": [1.0, "x", True], "c": [2.0]}))
    store = create_rate_limit_store(
        env={"QUODEQ_RATE_LIMIT_BACKEND": "file", "QUODEQ_RATE_LIMIT_FILE": str(path)},
    )

    assert store.check_and_record("a", now=3.0) is False
    # "x" and True are dropped, 1.0 is kept: one slot left, then limited.
    assert store.check_and_record("b", now=3.0) is False
    assert store.check_and_record("b", now=3.0) is True
    assert store.check_and_record("c", now=3.0) is False
    assert store.check_and_record("c", now=3.0) is True


def test_file_store_tolerates_a_state_file_that_is_not_utf8(tmp_path):
    """A state file holding bytes that are not UTF-8 reads as empty state
    instead of raising on every request."""
    from quodeq.api.app import create_rate_limit_store

    path = tmp_path / "rl.json"
    path.write_bytes(b"\xff")
    store = create_rate_limit_store(
        env={"QUODEQ_RATE_LIMIT_BACKEND": "file", "QUODEQ_RATE_LIMIT_FILE": str(path)},
    )

    assert store.check_and_record("a", now=1.0) is False
