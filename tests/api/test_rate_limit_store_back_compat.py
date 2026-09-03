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
