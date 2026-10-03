"""CSP same-origin ws computation failures.

``_add_security_headers`` (api/security.py) runs on *every* response via
``after_request``. Before this fix, a failure inside
``_same_origin_ws_sources`` was swallowed by a bare ``except Exception:
self_ws = ""`` with no trace at all -- a security control (the same-origin
websocket connect-src entry) could silently degrade repo-wide. The only
expected failure mode is a bad/attacker-controlled Host header, which
``request.host`` surfaces as ``werkzeug.exceptions.SecurityError``; these
tests force that failure and assert it is now observable, that the response
still completes with the safe fallback, and that repeated failures within
the cooldown window don't turn the failure itself into a new source of log
spam. A failure of any other type is a real bug in the ws-source
computation, not a bad Host header, so it now escapes instead of being
swallowed (covered separately below).
"""
from __future__ import annotations

import logging

import pytest
from werkzeug.exceptions import SecurityError

from quodeq.api import security as security_module
from quodeq.api.app import create_app

_FAILURE_MARKER = "CSP same-origin ws"


def _boom(_host: str) -> str:
    raise SecurityError("host parse exploded")


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
    assert "SecurityError" in matching[0].getMessage()


def test_csp_header_failure_log_is_rate_limited_across_responses(monkeypatch, security_caplog):
    """This except block fires on every response. A sustained failure must
    log once (so it's still discoverable), not once per request (so the
    failure itself can't become an unbounded log source).
    """
    caplog = security_caplog
    monkeypatch.setattr(security_module, "_same_origin_ws_sources", _boom)

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


def test_csp_header_first_failure_logs_on_freshly_booted_machine(monkeypatch, security_caplog):
    """The throttle's "never logged yet" state must not be
    a plain 0.0, because time.monotonic() is seconds-since-boot on every
    platform we ship to. On a machine up for less than the cooldown window
    (a desktop app launched at login), ``now - 0.0 < 60`` was true and the
    very first failure was silently dropped -- the exact silence this site
    was fixed to remove.
    """
    import types

    caplog = security_caplog
    monkeypatch.setattr(security_module, "_same_origin_ws_sources", _boom)
    # Clock says the machine has been up for 5 s.
    monkeypatch.setattr(security_module, "time", types.SimpleNamespace(monotonic=lambda: 5.0))

    app = create_app()
    with app.test_client() as client:
        resp = client.get("/api/health")

    assert resp.status_code == 200
    matching = [r for r in caplog.records if _FAILURE_MARKER in r.message]
    assert len(matching) == 1, (
        "the first failure after boot must be logged even when uptime < cooldown; "
        f"got {len(matching)} records"
    )


def test_csp_header_logging_cannot_break_response_even_if_a_handler_raises(monkeypatch):
    """A misbehaving handler must be contained by the handler contract
    (handleError), so the response still completes with the safe fallback."""
    monkeypatch.setattr(security_module, "_same_origin_ws_sources", _boom)

    class _ExplodingHandler(logging.Handler):
        def emit(self, record):
            try:
                raise RuntimeError("logging handler exploded")
            except RuntimeError:
                self.handleError(record)

    handler = _ExplodingHandler()
    security_module._logger.addHandler(handler)
    monkeypatch.setattr(logging, "raiseExceptions", False)  # keep the traceback off the test's stderr
    try:
        app = create_app()
        with app.test_client() as client:
            resp = client.get("/api/health")
    finally:
        security_module._logger.removeHandler(handler)

    assert resp.status_code == 200
    assert "wss://" not in resp.headers["Content-Security-Policy"]


def test_csp_header_propagates_a_failure_outside_the_narrowed_tuple(monkeypatch):
    """A RuntimeError (not a werkzeug SecurityError) from
    _same_origin_ws_sources is a real bug in the computation, not a bad Host
    header, so it now escapes the after_request hook. Flask's own exception
    handling turns that into a plain 500 for the client -- it does not crash
    the process or leave the response half-built."""
    def _real_bug(_host: str) -> str:
        raise RuntimeError("host parse exploded")

    monkeypatch.setattr(security_module, "_same_origin_ws_sources", _real_bug)

    app = create_app()
    with app.test_client() as client:
        resp = client.get("/api/health")

    assert resp.status_code == 500
