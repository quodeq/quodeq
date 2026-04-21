# tests/api/test_log_stream_registered.py
"""Route registration + auth coverage for log-stream endpoints."""
from __future__ import annotations

from http import HTTPStatus

from quodeq.api.app import create_app


def test_log_stream_routes_registered() -> None:
    app = create_app()
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/api/jobs/<job_id>/logs" in rules
    assert "/api/jobs/<job_id>/logs/stream" in rules


def test_log_stream_routes_require_auth_when_api_key_set() -> None:
    """With QUODEQ_API_KEY set, requests without Bearer token must be rejected."""
    app = create_app(api_key="secret")
    client = app.test_client()
    resp_plain = client.get("/api/jobs/some-job/logs")
    resp_stream = client.get("/api/jobs/some-job/logs/stream")
    # 401 from the global before_request hook. The plain endpoint may return
    # 404 FIRST if auth is skipped — fail loudly if that happens.
    assert resp_plain.status_code == HTTPStatus.UNAUTHORIZED, \
        f"plain_logs not auth-protected: got {resp_plain.status_code}"
    assert resp_stream.status_code == HTTPStatus.UNAUTHORIZED, \
        f"stream_logs not auth-protected: got {resp_stream.status_code}"
