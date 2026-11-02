"""Refuse local API requests that do not come from the Quodeq UI.

Loopback is not a trust boundary: an analysis agent the API spawned runs on
the same machine and can reach it with curl, which ignores the Origin check.
So every ``/api`` request must carry this launch's secret, in one of three
places the UI controls and the agent does not know:

* the ``quodeq_session_<port>`` cookie (HttpOnly, SameSite=Strict) the browser
  gets by opening a single-use launch link, ``/api/session/open?code=...``;
* the desktop window's User-Agent, ``QuodeqWebviewToken/<secret>`` (it cannot
  attach a cookie or header to its own navigations);
* the ``X-Quodeq-Session`` header, for the launcher, the window's native calls
  and the menubar, which read the secret from the 0600 session file.

Remote mode (``QUODEQ_API_KEY``) keeps its Bearer check and skips this one.
"""
from __future__ import annotations

import atexit
import hmac
import sys
import threading
import time
from http import HTTPStatus

from flask import Flask, Response, jsonify, redirect, request

from quodeq.api.helpers import json_error
from quodeq.shared.api_session import (
    SESSION_CODE_PATH,
    SESSION_COOKIE,
    SESSION_HEADER,
    SESSION_OPEN_PATH as OPEN_PATH,
    WEBVIEW_TOKEN_UA_PREFIX,
    mint_session_secret,
    remove_session_file,
    write_session_file,
)
from quodeq.shared.utils import get_action_api_host, get_action_api_port

CONFIG_SECRET = "QUODEQ_SESSION_SECRET"  # test_config may pin it; otherwise minted per app
CODE_SESSION_REQUIRED = "SESSION_REQUIRED"
# Reachable without a session: the liveness probe every launcher, CLI command
# and the menubar use, and the link that turns a launch code into a cookie.
OPEN_PATHS = frozenset({"/api/health", OPEN_PATH})
_CODE_TTL_S = 120.0
_CODE_LEN = 16

_REQUIRED_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Quodeq</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 32rem; margin: 6rem auto; padding: 0 1rem;">
<h1 style="font-size: 1.25rem;">Open Quodeq from your terminal</h1>
<p>{reason} Run <code>quodeq dashboard</code> to open the app, or
<code>quodeq dashboard --browser</code> to open it in this browser.</p>
</body></html>"""
_REASON_NO_SESSION = "This page only answers the Quodeq app it was launched for."
_REASON_BAD_CODE = "This launch link has expired or was already used."


def _webview_token_from_ua(user_agent: str) -> str | None:
    idx = user_agent.find(WEBVIEW_TOKEN_UA_PREFIX)
    if idx == -1:
        return None
    candidate = user_agent[idx + len(WEBVIEW_TOKEN_UA_PREFIX):].split(" ", 1)[0]
    # hmac.compare_digest raises TypeError on a non-ASCII str, and Werkzeug
    # decodes headers as latin-1, so a UA byte >= 0x80 would 500 every
    # request from inside after_request. The real secret is always ASCII, so
    # a non-ASCII candidate can never match: fail closed like a wrong one.
    return candidate if candidate and candidate.isascii() else None


def _same(candidate: str | None, expected: str | None) -> bool:
    if not candidate or not expected or not candidate.isascii() or not expected.isascii():
        return False
    return hmac.compare_digest(candidate, expected)


def is_trusted_webview(user_agent: str, expected: str | None) -> bool:
    """True only for a User-Agent carrying this launch's secret."""
    return _same(_webview_token_from_ua(user_agent), expected)


class SessionAuth:
    """This app's secret plus the single-use launch codes it has handed out."""

    def __init__(self, secret: str, cookie_name: str) -> None:
        self.secret = secret
        self.cookie_name = cookie_name
        self._codes: dict[str, float] = {}
        self._lock = threading.Lock()

    def issue_code(self) -> str:
        """A single-use launch code, valid for _CODE_TTL_S; expired ones are dropped here."""
        code = mint_session_secret()[:_CODE_LEN]
        now = time.monotonic()
        with self._lock:
            self._codes = {c: exp for c, exp in self._codes.items() if exp > now}
            self._codes[code] = now + _CODE_TTL_S
        return code

    def redeem(self, code: str) -> bool:
        """Spend *code*: True once, while it is still fresh."""
        with self._lock:
            expires = self._codes.pop(code, None)
        return expires is not None and expires > time.monotonic()

    def header_ok(self) -> bool:
        """The header proves a non-browser caller: a page cannot set it cross-site."""
        return _same(request.headers.get(SESSION_HEADER), self.secret)

    def request_ok(self) -> bool:
        """True when the current request carries the secret by header, cookie or window UA."""
        return (
            self.header_ok()
            or _same(request.cookies.get(self.cookie_name), self.secret)
            or is_trusted_webview(request.headers.get("User-Agent", ""), self.secret)
        )


def _required_page(reason: str) -> tuple[str, int, dict[str, str]]:
    return _REQUIRED_PAGE.format(reason=reason), HTTPStatus.UNAUTHORIZED, {"Content-Type": "text/html"}


def check_session(session: SessionAuth) -> Response | tuple | None:
    """Refuse a request without this launch's secret; None lets it through.

    Static assets (any path with a file extension) stay public: they are the
    same bundle every install ships. The SPA page itself and every ``/api``
    route are not.
    """
    path = request.path
    if path in OPEN_PATHS or session.request_ok():
        return None
    if path.startswith("/api/"):
        return json_error("Open Quodeq from your terminal to get a session",
                          HTTPStatus.UNAUTHORIZED, CODE_SESSION_REQUIRED)
    if "." in path.rsplit("/", 1)[-1]:
        return None
    return _required_page(_REASON_NO_SESSION)


def _register_routes(app: Flask, session: SessionAuth) -> None:
    @app.get(OPEN_PATH)
    def session_open() -> Response | tuple:
        if not session.redeem(request.args.get("code", "")):
            return _required_page(_REASON_BAD_CODE)
        response = redirect("/", code=HTTPStatus.FOUND)
        response.set_cookie(session.cookie_name, session.secret, httponly=True, samesite="Strict", path="/")
        return response

    @app.post(SESSION_CODE_PATH)
    def session_code() -> Response:
        code = session.issue_code()
        return jsonify({"code": code, "path": f"{OPEN_PATH}?code={code}"})


def install_session_auth(app: Flask, env: dict[str, str] | None = None) -> SessionAuth:
    """Give *app* its secret and the launch-link routes."""
    secret = app.config.get(CONFIG_SECRET) or mint_session_secret()
    session = SessionAuth(secret, f"{SESSION_COOKIE}_{get_action_api_port(env)}")
    app.extensions["session_auth"] = session
    _register_routes(app, session)
    return session


def publish_session(app: Flask, env: dict[str, str] | None = None) -> None:
    """main() only: write the secret to the run dir for this port, removed on exit.

    A standalone ``quodeq api`` in a terminal also prints a launch link, since
    no launcher is there to open one.
    """
    session: SessionAuth = app.extensions["session_auth"]
    port = get_action_api_port(env)
    write_session_file(port, session.secret, env)
    atexit.register(remove_session_file, port, session.secret, env)
    if sys.stdout is not None and sys.stdout.isatty():
        host = get_action_api_host(env)
        print(f"Open Quodeq: http://{host}:{port}{OPEN_PATH}?code={session.issue_code()}", flush=True)
