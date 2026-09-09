"""Audit log records the request outcome, not just that a request was attempted (Task 11)."""
from __future__ import annotations

import logging

from quodeq.api.app import create_app


def _allow_propagation():
    """create_app() sets quodeq.api's propagate=False so its own handler
    (the ring-buffer log) is the only sink and console output isn't
    duplicated. caplog's handler sits on the root logger, so records must
    be allowed to propagate there for the duration of the test."""
    logger = logging.getLogger("quodeq.api")
    original = logger.propagate
    logger.propagate = True
    return logger, original


def test_audit_log_includes_method_path_and_status(caplog):
    app = create_app()
    client = app.test_client()
    logger, orig = _allow_propagation()
    try:
        with caplog.at_level(logging.INFO, logger="quodeq.api.security"):
            resp = client.get("/api/health")
    finally:
        logger.propagate = orig

    assert resp.status_code == 200
    lines = [r.getMessage() for r in caplog.records if r.name == "quodeq.api.security"]
    assert len(lines) == 1
    line = lines[0]
    assert "GET" in line
    assert "/api/health" in line
    assert "200" in line


def test_audit_log_records_denied_outcome_status(caplog):
    """A rejected request (missing Origin on a state-changing call) must log
    its actual denied status, not a blanket "attempted" line with no result."""
    app = create_app(api_key="test-key")
    client = app.test_client()
    logger, orig = _allow_propagation()
    try:
        with caplog.at_level(logging.INFO, logger="quodeq.api.security"):
            resp = client.post(
                "/api/findings/dismiss",
                headers={"Authorization": "Bearer test-key"},
            )
    finally:
        logger.propagate = orig

    assert resp.status_code == 403
    lines = [r.getMessage() for r in caplog.records if r.name == "quodeq.api.security"]
    assert len(lines) == 1
    line = lines[0]
    assert "POST" in line
    assert "/api/findings/dismiss" in line
    assert "403" in line


def test_audit_log_includes_actor_when_api_key_set(caplog):
    app = create_app(api_key="test-key")
    client = app.test_client()
    logger, orig = _allow_propagation()
    try:
        with caplog.at_level(logging.INFO, logger="quodeq.api.security"):
            resp = client.get(
                "/api/health", headers={"Authorization": "Bearer test-key"}
            )
    finally:
        logger.propagate = orig

    assert resp.status_code == 200
    lines = [r.getMessage() for r in caplog.records if r.name == "quodeq.api.security"]
    assert len(lines) == 1
    assert "actor=key:***" in lines[0]


def test_audit_log_emits_exactly_once_per_request(caplog):
    """Regression: the request must be logged once with the outcome, not
    twice (once before the response, once after)."""
    app = create_app()
    client = app.test_client()
    logger, orig = _allow_propagation()
    try:
        with caplog.at_level(logging.INFO, logger="quodeq.api.security"):
            client.get("/api/health")
    finally:
        logger.propagate = orig

    lines = [r.getMessage() for r in caplog.records if r.name == "quodeq.api.security"]
    assert len(lines) == 1
