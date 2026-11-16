"""Autouse: Flask test clients carry the app's session cookie, as the real UI does.

The local API refuses any ``/api`` request without this launch's secret
(``quodeq.api.session_auth``). Route tests exercise what the UI can do, so
their clients start with the cookie the launch link would have set; the
refusal itself is tested with a bare ``FlaskClient`` (``unauthenticated_client``).
The isolated run dir keeps any session file a test publishes out of
``~/.quodeq/run``.
"""
from __future__ import annotations

import pytest
from flask import Flask
from flask.testing import FlaskClient


class SessionClient(FlaskClient):
    """Sends the session cookie whatever Host a test targets.

    A jar cookie only goes to the domain it was set for, and tests address
    the app as localhost, 127.0.0.1, [::1] and spoofed hosts alike.
    """

    def _add_cookies_to_wsgi(self, environ) -> None:
        super()._add_cookies_to_wsgi(environ)
        session = self.application.extensions.get("session_auth")
        if session is None:
            return
        existing = environ.get("HTTP_COOKIE", "")
        if f"{session.cookie_name}=" not in existing:
            ours = f"{session.cookie_name}={session.secret}"
            environ["HTTP_COOKIE"] = f"{existing}; {ours}" if existing else ours


def unauthenticated_client(app: Flask) -> FlaskClient:
    """A client with no session: what curl from an analysis agent looks like."""
    return FlaskClient(app, app.response_class, use_cookies=True)


@pytest.fixture(autouse=True)
def _session_test_client(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    monkeypatch.setattr(Flask, "test_client_class", SessionClient)
    monkeypatch.setenv("QUODEQ_RUN_DIR", str(tmp_path_factory.mktemp("quodeq-run")))
