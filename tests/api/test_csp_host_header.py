"""Host header validation before CSP interpolation (Task 9).

Split out of test_csp_header.py when that file crossed the 300-line cap.
"""
from __future__ import annotations

from tests.api._csp_helpers import _ALT_PORT_ORIGINS, _csp_for_host, _directive


def test_csp_same_origin_ws_uses_valid_host():
    """A well-formed Host header still gets an explicit same-origin ws/wss entry."""
    connect_src = _directive(_csp_for_host("example.com:8080"), "connect-src")
    assert connect_src is not None
    tokens = connect_src.split()
    assert "ws://example.com:8080" in tokens
    assert "wss://example.com:8080" in tokens


def test_csp_omits_same_origin_ws_for_malicious_host_header():
    """A malicious Host header must not be interpolated raw into the CSP.

    Regression for the finding: connect-src was built from the raw,
    unvalidated Host header, so a Host containing a quote/space could inject
    extra CSP sources or directives. Invalid hosts must have the same-origin
    ws:/wss: entry omitted entirely rather than reflected into the header.
    """
    malicious_host = 'evil.example" ws://attacker.evil'
    csp = _csp_for_host(malicious_host)

    # The raw malicious host must never appear verbatim in the header.
    assert malicious_host not in csp
    assert '"' not in csp
    assert "attacker.evil" not in csp

    connect_src = _directive(csp, "connect-src")
    assert connect_src is not None
    # Same-origin ws/wss entries for the bogus host must be absent.
    assert "evil.example" not in connect_src
    # The rest of connect-src (alt-port origins) must still be present —
    # omission of the same-origin entry must not break the whole directive.
    assert "'self'" in connect_src
    for origin in _ALT_PORT_ORIGINS:
        assert origin in connect_src


def test_csp_same_origin_ws_uses_bracketed_ipv6_host_with_port():
    """A bracketed IPv6-literal Host header (RFC 3986 syntax) with a port
    still gets an explicit same-origin ws/wss entry.

    ::1 is a first-class local address elsewhere in this app
    (_LOCALHOST_ADDRS, dashboard/_networking.py's _DEFAULT_LOCAL_HOSTS,
    dashboard/_webview_window_native_ops.py's reload allowlist), so a
    client reaching the dashboard over IPv6 loopback is a real access
    path — the same-origin entry must not be silently dropped for it.
    """
    connect_src = _directive(_csp_for_host("[::1]:4180"), "connect-src")
    assert connect_src is not None
    tokens = connect_src.split()
    assert "ws://[::1]:4180" in tokens
    assert "wss://[::1]:4180" in tokens


def test_csp_same_origin_ws_uses_bracketed_ipv6_host_without_port():
    """A bracketed IPv6-literal Host header with no port also validates.

    Werkzeug/Flask preserve the Host header verbatim on request.host, so a
    bare "[::1]" (no ":port") is a value it can actually take.
    """
    connect_src = _directive(_csp_for_host("[::1]"), "connect-src")
    assert connect_src is not None
    tokens = connect_src.split()
    assert "ws://[::1]" in tokens
    assert "wss://[::1]" in tokens
