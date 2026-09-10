"""Cluster 17 site 2 regression: CSP same-origin ws computation failures.

``_add_security_headers`` (api/security.py) runs on *every* response via
``after_request``. Before this fix, a failure inside
``_same_origin_ws_sources`` was swallowed by a bare ``except Exception:
self_ws = ""`` with no trace at all -- a security control (the same-origin
websocket connect-src entry) could silently degrade repo-wide. These tests
force that failure and assert it is now observable, that the response still
completes with the safe fallback, and that repeated failures within the
cooldown window don't turn the failure itself into a new source of log spam.
"""
from __future__ import annotations

import logging

import pytest

from quodeq.api import security as security_module
from quodeq.api.app import create_app

_FAILURE_MARKER = "CSP same-origin ws"


def _boom(_host: str) -> str:
    raise RuntimeError("host parse exploded")


def _reset_throttle(monkeypatch) -> None:
    # Each test gets a fresh cooldown window regardless of module import
    # order / earlier tests in the same process.
    monkeypatch.setattr(security_module, "_last_csp_ws_failure_log_at", 0.0)


@pytest.fixture
def security_caplog(caplog):
    """caplog, wired to actually see quodeq.api.security records.

    api/app.py's _configure_logging sets the *parent* "quodeq.api" logger to
    ``propagate = False`` with its own handlers -- but only once ``create_app()``
    runs, which happens inside the test body, after pytest's caplog fixture has
    already taken its one-time snapshot of non-propagating loggers to attach to
    (see _pytest.logging.catching_logs.__enter__). So caplog's root-attached
    handler never sees these records. Attach it directly to the
    "quodeq.api.security" logger itself instead, which sidesteps the parent's
    propagate setting entirely (a logger always runs its own handlers before
    consulting propagate).
    """
    logger = logging.getLogger("quodeq.api.security")
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.WARNING, logger="quodeq.api.security")
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)


def test_csp_header_logs_and_falls_back_on_same_origin_ws_failure(monkeypatch, security_caplog):
    """The failure must be logged, and the response must still succeed with
    the same-origin ws/wss entry omitted (not reflect a crash to the client).
    """
    caplog = security_caplog
    monkeypatch.setattr(security_module, "_same_origin_ws_sources", _boom)
    _reset_throttle(monkeypatch)

    app = create_app()
    with app.test_client() as client:
        resp = client.get("/api/health")

    assert resp.status_code == 200
    csp = resp.headers["Content-Security-Policy"]
    # Only _same_origin_ws_sources ever emits a wss:// token (the alt-port
    # origins are http:// and ws:// only) -- its absence confirms the "" fallback
    # landed, i.e. the response degraded safely instead of crashing.
    assert "wss://" not in csp
    assert "connect-src" in csp

    matching = [r for r in caplog.records if _FAILURE_MARKER in r.message]
    assert matching, f"expected the failure to be logged; got: {[r.message for r in caplog.records]}"
    assert matching[0].levelno == logging.WARNING
    # No raw request data (host/headers) in the message -- only the
    # exception's type name, so nothing attacker-controlled reaches the log.
    assert "RuntimeError" in matching[0].getMessage()


def test_csp_header_failure_log_is_rate_limited_across_responses(monkeypatch, security_caplog):
    """This except block fires on every response. A sustained failure must
    log once (so it's still discoverable), not once per request (so the
    failure itself can't become an unbounded log source).
    """
    caplog = security_caplog
    monkeypatch.setattr(security_module, "_same_origin_ws_sources", _boom)
    _reset_throttle(monkeypatch)

    app = create_app()
    with app.test_client() as client:
        for _ in range(5):
            resp = client.get("/api/health")
            assert resp.status_code == 200

    matching = [r for r in caplog.records if _FAILURE_MARKER in r.message]
    assert len(matching) == 1, (
        "5 consecutive failures inside the cooldown window must log once, "
        f"not per-response; got {len(matching)}"
    )


def test_csp_header_logging_cannot_break_response_even_if_logger_raises(monkeypatch, caplog):
    """The log call itself must be provably safe: even if logging blows up
    (e.g. a misbehaving handler), the response must still complete with the
    safe fallback rather than turning into a 500.
    """
    monkeypatch.setattr(security_module, "_same_origin_ws_sources", _boom)
    _reset_throttle(monkeypatch)

    def _raising_warning(*_args, **_kwargs):
        raise RuntimeError("logging handler exploded")

    monkeypatch.setattr(security_module._logger, "warning", _raising_warning)

    app = create_app()
    with app.test_client() as client:
        resp = client.get("/api/health")

    assert resp.status_code == 200
    assert "wss://" not in resp.headers["Content-Security-Policy"]
