"""Regression: findings-mutation endpoints must not be rate-limited.

The user's UX is to burst-dismiss many findings in quick succession on
large projects. The legacy 60/min/IP cap turned the 61st click into a 429,
which the frontend handled by rolling back its optimistic update — so
violations appeared to "come back" to the user after several were dismissed
rapidly. These tests pin the new behaviour:

* ``/api/findings/dismiss`` / ``restore`` / ``delete`` are exempt from
  rate limiting entirely (they're idempotent user actions).
* Other state-changing POSTs still hit the global limit.
"""
from __future__ import annotations

import os
import pytest

from quodeq.api.app import create_app
from quodeq.api._rate_limit_store import InMemoryRateLimitStore


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Full Flask app stack with a *tight* rate limit so the burst test is fast."""
    monkeypatch.setenv("QUODEQ_RATE_LIMIT_MAX", "5")
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path))
    # Use a fresh in-memory store with the same tight cap so the test
    # doesn't depend on environment-reading inside the factory.
    store = InMemoryRateLimitStore(window=60, max_requests=5)
    app = create_app(rate_limit_store=store)
    return app.test_client()


_DISMISS_BODY = {
    "project": "p",
    "req": "R1",
    "file": "a.py",
    "line": 1,
    "dimension": "security",
    "severity": "minor",
}


def test_dismiss_endpoint_is_exempt_from_rate_limit(client):
    """Bursting more dismisses than the rate-limit cap must NOT return 429."""
    # The cap is 5/min via the fixture — fire 20 dismisses in a row.
    for i in range(20):
        body = {**_DISMISS_BODY, "line": i}
        resp = client.post(
            "/api/findings/dismiss",
            json=body,
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 200, (
            f"dismiss #{i} returned {resp.status_code} {resp.data!r} — "
            f"findings-mutation endpoints must be exempt from rate limiting"
        )


def test_restore_endpoint_is_exempt_from_rate_limit(client):
    for i in range(20):
        resp = client.post(
            "/api/findings/restore",
            json={"project": "p", "req": "R1", "file": "a.py", "line": i},
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 200, (
            f"restore #{i} returned {resp.status_code}"
        )


def test_delete_endpoint_is_exempt_from_rate_limit(client):
    for i in range(20):
        resp = client.post(
            "/api/findings/delete",
            json={
                "project": "p",
                "dimension": "security",
                "principle": "Integrity",
                "file": f"a-{i}.py",
            },
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 200, (
            f"delete #{i} returned {resp.status_code}"
        )


def test_non_findings_post_still_rate_limited(client):
    """Other state-changing POSTs still respect the global cap.

    Pins that the exemption doesn't accidentally disable rate limiting for
    everything — e.g. ``/api/projects/<p>`` DELETE or ``/api/evaluations``
    POST should still hit 429 after the cap.
    """
    # 6th call past the cap-of-5 should return 429.
    last_status = None
    for _ in range(10):
        resp = client.post(
            "/api/evaluations",
            json={},
            headers={"Origin": "http://localhost"},
        )
        last_status = resp.status_code
        if last_status == 429:
            break
    assert last_status == 429, (
        f"Expected /api/evaluations to be rate-limited after the cap, got {last_status}"
    )
