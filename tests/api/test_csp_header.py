"""CSP header hardening regression tests (held security fix #40).

Base directive coverage. Split when this file crossed the 300-line cap: the
webview-token relaxation now lives in test_csp_webview_token.py and the
Host-header validation in test_csp_host_header.py, with the shared request
helpers in _csp_helpers.py.
"""
from __future__ import annotations

import pytest

from quodeq.api import security
from quodeq.api.app import create_app
from tests.api._csp_helpers import _ALT_PORT_ORIGINS, _WS_ALT_PORT_ORIGINS, _directive


@pytest.fixture(scope="module")
def csp():
    app = create_app()
    with app.test_client() as client:
        resp = client.get("/api/health")
        return resp.headers["Content-Security-Policy"]


def test_csp_restricts_egress(csp):
    """CSP must cap exfiltration of the API key stored in localStorage."""
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp   # keep existing


def test_csp_no_unsafe_eval_or_inline_scripts(csp):
    """script-src must not permit unsafe-inline or unsafe-eval (defeats XSS protection)."""
    # These would open the door to XSS-based exfil
    assert "'unsafe-eval'" not in csp

    # script-src must not carry unsafe-inline (style-src may, for React).
    # Match by exact directive keyword to avoid accidentally matching script-src-elem.
    script_src = _directive(csp, "script-src")
    assert script_src is not None, "script-src must be present in CSP"
    assert "'unsafe-inline'" not in script_src, "script-src must not contain 'unsafe-inline'"
    assert "'unsafe-eval'" not in script_src, "script-src must not contain 'unsafe-eval'"


def test_csp_allows_google_fonts(csp):
    """CSP must allow Google Fonts (used by the dashboard) to avoid breaking the UI."""
    assert "fonts.googleapis.com" in csp
    assert "fonts.gstatic.com" in csp


def test_alt_port_origins_built_once_as_module_constant(csp):
    """The alt-port list depends on no request data, so it is built at import
    and interpolated per response rather than re-joined in after_request."""
    constant = security._ALT_PORT_ORIGINS
    assert isinstance(constant, str)
    tokens = constant.split()
    for origin in _ALT_PORT_ORIGINS + _WS_ALT_PORT_ORIGINS:
        assert origin in tokens
    assert constant in _directive(csp, "connect-src")


def test_csp_connect_src_includes_alt_port_origins(csp):
    """connect-src must list the alt-port loopback origins probed by useServerHealth.js.

    useServerHealth.js's altPortCandidates() scans DASHBOARD_BASE_PORT (7863)
    through PORT_SCAN_SPAN (5) ports: 7863-7867. The hook calls
    fetch(`${baseUrl}:${port}/api/health`) where baseUrl defaults to
    http://127.0.0.1, so each probe is a cross-origin request that requires
    an explicit connect-src entry.
    """
    connect_src = _directive(csp, "connect-src")
    assert connect_src is not None, "connect-src must be present in CSP"
    assert "'self'" in connect_src, "connect-src must keep 'self'"
    for origin in _ALT_PORT_ORIGINS:
        assert origin in connect_src, (
            f"connect-src must include alt-port origin {origin!r} "
            f"(probed by useServerHealth.js)"
        )


def test_csp_connect_src_includes_ws_sources(csp):
    """connect-src must list ws:// sources for the terminal WebSocket (Task 5).

    WebKit/pywebview enforces CSP against the WebSocket handshake's scheme,
    so the terminal's ws:// connection to the alt-port server and to the
    same-origin server both need explicit connect-src entries — the http://
    alt-port origins already covered by
    test_csp_connect_src_includes_alt_port_origins do not authorize ws://.
    """
    connect_src = _directive(csp, "connect-src")
    assert connect_src is not None, "connect-src must be present in CSP"

    # Spot-check loopback alt-port ws origins, then check the full set.
    assert "ws://127.0.0.1:7863" in connect_src
    assert "ws://localhost:7867" in connect_src
    for origin in _WS_ALT_PORT_ORIGINS:
        assert origin in connect_src, (
            f"connect-src must include ws alt-port origin {origin!r} "
            f"(terminal WebSocket, Task 5)"
        )

    # Same-origin ws source for the request's host. The Flask test client
    # sends Host: localhost, so request.host renders as bare "localhost"
    # (no port) — check exact tokens to avoid matching the ws://localhost:PORT
    # alt-port entries above as a false-positive substring.
    tokens = connect_src.split()
    assert "ws://localhost" in tokens, "connect-src must include same-origin ws:// source"
    assert "wss://localhost" in tokens, "connect-src must include same-origin wss:// source"

    # Regression guard: adding ws:// sources must be additive, not a swap —
    # the pre-existing http:// alt-port origins must still be present.
    for origin in _ALT_PORT_ORIGINS:
        assert origin in connect_src, (
            f"connect-src must still include http alt-port origin {origin!r} "
            f"(regression: ws:// sources must not replace http:// ones)"
        )


def test_csp_mask_src_allows_data_uris(csp):
    """mask-src must allow data: URIs for inline SVG mask icons (evaluation.css).

    Without mask-src the directive falls back to default-src 'self', which
    blocks data: URIs and breaks the folder icon in the evaluation view.
    """
    mask_src = _directive(csp, "mask-src")
    assert mask_src is not None, "mask-src must be present in CSP"
    assert "data:" in mask_src, "mask-src must include data: to allow inline SVG masks"
