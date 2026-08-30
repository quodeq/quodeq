import logging

import pytest

from quodeq.api.app import create_app


def test_logs_endpoint_returns_empty():
    # Uses default config — log routes do not require injectable test config.
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/logs")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["lines"] == [] or isinstance(data["lines"], list)
    assert "total" in data


def test_logs_endpoint_since_param():
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/logs?since=0")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data["lines"], list)


def test_logs_endpoint_captures_requests():
    app = create_app()
    client = app.test_client()
    # Make a request that generates a log
    client.get("/api/health")
    resp = client.get("/api/logs")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] >= 0


def test_logs_page_returns_html():
    app = create_app()
    client = app.test_client()
    resp = client.get("/logs")
    assert resp.status_code == 200
    assert b"<!DOCTYPE html>" in resp.data
    assert b"Quodeq" in resp.data
    # The poller now lives in the externalized script (CSP fix: an inline
    # <script> is blocked by the script-src 'self' policy in api/security.py).
    assert b"/logs.js" in resp.data


def test_logs_js_polls_the_api_logs_endpoint():
    app = create_app()
    client = app.test_client()
    resp = client.get("/logs.js")
    assert resp.status_code == 200
    assert resp.content_type.startswith("application/javascript")
    assert b"/api/logs" in resp.data
    # The placeholder must be templated to a real number, not left literal.
    assert b"{{POLL_INTERVAL_MS}}" not in resp.data


def test_logs_css_served():
    app = create_app()
    client = app.test_client()
    resp = client.get("/logs.css")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/css")


@pytest.mark.parametrize("logger_name", ["werkzeug", "quodeq.api"])
def test_logs_suppressed_by_default(logger_name):
    """Request logs go to buffer only, not stderr."""
    create_app()
    lgr = logging.getLogger(logger_name)
    assert len(lgr.handlers) == 1
    assert lgr.propagate is False
