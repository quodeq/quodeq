"""CSP header hardening regression tests (held security fix #40)."""
from __future__ import annotations

import pytest

from quodeq.api.app import create_app

# Alt-port origins probed by useServerHealth.js (DEFAULT_ALT_PORTS = [4180..4183]).
_ALT_PORT_ORIGINS = [
    f"http://127.0.0.1:{p}" for p in (4180, 4181, 4182, 4183)
] + [
    f"http://localhost:{p}" for p in (4180, 4181, 4182, 4183)
]


@pytest.fixture(scope="module")
def csp():
    app = create_app()
    with app.test_client() as client:
        resp = client.get("/api/health")
        return resp.headers["Content-Security-Policy"]


def _directive(csp: str, name: str) -> str | None:
    """Return the first CSP directive whose keyword exactly equals *name*."""
    for d in csp.split(";"):
        parts = d.strip().split()
        if parts and parts[0] == name:
            return d.strip()
    return None


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


def test_csp_connect_src_includes_alt_port_origins(csp):
    """connect-src must list the alt-port loopback origins probed by useServerHealth.js.

    DEFAULT_ALT_PORTS = [4180, 4181, 4182, 4183] in useServerHealth.js.
    The hook calls fetch(`${baseUrl}:${port}/api/health`) where baseUrl
    defaults to http://127.0.0.1, so each probe is a cross-origin request
    that requires an explicit connect-src entry.
    """
    connect_src = _directive(csp, "connect-src")
    assert connect_src is not None, "connect-src must be present in CSP"
    assert "'self'" in connect_src, "connect-src must keep 'self'"
    for origin in _ALT_PORT_ORIGINS:
        assert origin in connect_src, (
            f"connect-src must include alt-port origin {origin!r} "
            f"(probed by useServerHealth.js)"
        )


def test_csp_mask_src_allows_data_uris(csp):
    """mask-src must allow data: URIs for inline SVG mask icons (evaluation.css).

    Without mask-src the directive falls back to default-src 'self', which
    blocks data: URIs and breaks the folder icon in the evaluation view.
    """
    mask_src = _directive(csp, "mask-src")
    assert mask_src is not None, "mask-src must be present in CSP"
    assert "data:" in mask_src, "mask-src must include data: to allow inline SVG masks"
