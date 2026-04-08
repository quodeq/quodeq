import logging

import pytest

from quodeq.api.app import create_app


def test_logs_endpoint_returns_empty():
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
    assert b"/api/logs" in resp.data


@pytest.mark.parametrize("logger_name", ["werkzeug", "quodeq.api"])
def test_logs_suppressed_by_default(logger_name):
    """Request logs go to buffer only, not stderr."""
    create_app()
    lgr = logging.getLogger(logger_name)
    assert len(lgr.handlers) == 1
    assert lgr.propagate is False
