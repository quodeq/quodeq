"""Shared helpers for the CSP header test modules.

Split out when test_csp_header.py crossed the 300-line file cap: the base
directive tests, the webview-token relaxation tests and the Host-header
validation tests now live in three siblings that all need these three
request helpers.
"""
from __future__ import annotations

from quodeq.api.app import create_app

# Alt-port origins probed by useServerHealth.js (DEFAULT_ALT_PORTS = [4180..4183]).
_ALT_PORT_ORIGINS = [
    f"http://127.0.0.1:{p}" for p in (4180, 4181, 4182, 4183)
] + [
    f"http://localhost:{p}" for p in (4180, 4181, 4182, 4183)
]

# ws:// alt-port origins for the terminal WebSocket (Task 5). WebKit/pywebview
# enforces CSP against the WebSocket handshake scheme, so http:// alone does
# not cover it — each alt port needs an explicit ws:// entry too.
_WS_ALT_PORT_ORIGINS = [
    f"ws://127.0.0.1:{p}" for p in (4180, 4181, 4182, 4183)
] + [
    f"ws://localhost:{p}" for p in (4180, 4181, 4182, 4183)
]


def _directive(csp: str, name: str) -> str | None:
    """Return the first CSP directive whose keyword exactly equals *name*."""
    for d in csp.split(";"):
        parts = d.strip().split()
        if parts and parts[0] == name:
            return d.strip()
    return None


def _csp_for_ua(ua: str | None) -> str:
    app = create_app()
    with app.test_client() as client:
        headers = {"User-Agent": ua} if ua is not None else {}
        return client.get("/api/health", headers=headers).headers["Content-Security-Policy"]


def _csp_for_host(host: str) -> str:
    app = create_app()
    with app.test_client() as client:
        return client.get(
            "/api/health", headers={"Host": host}
        ).headers["Content-Security-Policy"]
