"""Webview-only unsafe-eval relaxation, gated on the per-launch token.

Split out of test_csp_header.py when that file crossed the 300-line cap.

Held security fix: the relaxation used to be gated on the QuodeqDesktop UA
marker alone, a fixed public string any HTTP client could send. It is now
gated on the API's per-launch session secret embedded in the webview's own
UA, see quodeq.api.session_auth.is_trusted_webview.
"""
from __future__ import annotations

from quodeq.api import session_auth, security
from quodeq.api.app import create_app
from quodeq.shared.api_session import WEBVIEW_TOKEN_UA_PREFIX
from tests.api._csp_helpers import _csp_for_ua, _directive

_TOKEN = "shared-secret-abc123"
_WEBVIEW_UA_MARKER_ONLY = (
    "Mozilla/5.0 (quodeq) AppleWebKit/605.1.15 (KHTML, like Gecko) QuodeqDesktop/1.4.0 Safari/605.1.15"
)
_WEBVIEW_UA_WITH_TOKEN = (
    "Mozilla/5.0 (quodeq) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    f"QuodeqDesktop/1.4.0 {WEBVIEW_TOKEN_UA_PREFIX}{_TOKEN} Safari/605.1.15"
)


def test_webview_ua_with_correct_token_gets_unsafe_eval(monkeypatch):
    """The native webview UA, carrying the correct per-launch token, must be
    served script-src with 'unsafe-eval' so pywebview's new Function()
    bridge works under the otherwise-strict CSP."""
    script_src = _directive(_csp_for_ua(_WEBVIEW_UA_WITH_TOKEN, _TOKEN), "script-src")
    assert script_src is not None
    assert "'unsafe-eval'" in script_src


def test_forged_marker_without_token_stays_strict(monkeypatch):
    """The OLD static marker string alone, without the token, must NOT get
    the relaxed CSP — this is the forgery the token gate closes: any HTTP
    client can set a UA substring, so the marker alone must never be enough."""
    script_src = _directive(_csp_for_ua(_WEBVIEW_UA_MARKER_ONLY, _TOKEN), "script-src")
    assert script_src is not None
    assert "'unsafe-eval'" not in script_src


def test_wrong_token_stays_strict(monkeypatch):
    """A UA carrying a token that doesn't match the launch's secret must not
    get the relaxation either (not just any token-shaped string)."""
    wrong_ua = (
        "Mozilla/5.0 (quodeq) AppleWebKit/605.1.15 (KHTML, like Gecko) "
        f"QuodeqDesktop/1.4.0 {WEBVIEW_TOKEN_UA_PREFIX}not-the-real-token Safari/605.1.15"
    )
    script_src = _directive(_csp_for_ua(wrong_ua, _TOKEN), "script-src")
    assert script_src is not None
    assert "'unsafe-eval'" not in script_src


def test_a_fresh_launch_secret_never_matches_a_guessed_token():
    """Without a pinned secret the app mints its own, so no UA a client can
    guess ever wins the relaxation."""
    for ua in (_WEBVIEW_UA_WITH_TOKEN, _WEBVIEW_UA_MARKER_ONLY, "Mozilla/5.0 (a regular browser)"):
        script_src = _directive(_csp_for_ua(ua), "script-src")
        assert script_src is not None
        assert "'unsafe-eval'" not in script_src


def test_non_webview_ua_stays_strict(monkeypatch):
    """Any non-webview UA keeps the strict script-src (no unsafe-eval)."""
    script_src = _directive(_csp_for_ua("Mozilla/5.0 (a regular browser)", _TOKEN), "script-src")
    assert script_src is not None
    assert "'unsafe-eval'" not in script_src


def test_non_ascii_ua_token_does_not_crash_and_stays_strict(monkeypatch):
    """A UA carrying a non-ASCII byte inside the token must fail closed, not 500.

    Regression: Werkzeug decodes headers as latin-1, so any UA byte >= 0x80
    reaches _webview_token_from_ua as a non-ASCII str, and
    hmac.compare_digest raises TypeError on one. That fired inside the
    after_request hook, so EVERY request 500'd with none of the security
    headers set whenever QUODEQ_WEBVIEW_TOKEN was set (the normal desktop
    launcher path). The candidate must be dropped instead, exactly like any
    other non-matching token.
    """
    hostile_ua = (
        "Mozilla/5.0 (quodeq) QuodeqDesktop/1.4.0 "
        f"{WEBVIEW_TOKEN_UA_PREFIX}tøken Safari/605.1.15"
    )
    app = create_app(test_config={session_auth.CONFIG_SECRET: _TOKEN})
    with app.test_client() as client:
        resp = client.get("/api/health", headers={"User-Agent": hostile_ua})

    assert resp.status_code == 200
    # The security headers must all still be present (they were not on the 500).
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    script_src = _directive(resp.headers["Content-Security-Policy"], "script-src")
    assert script_src is not None
    assert "'unsafe-eval'" not in script_src, "a non-ASCII token must fail closed"


def test_non_ascii_expected_secret_does_not_crash_and_stays_strict():
    """The OTHER side of compare_digest. It raises TypeError if EITHER str is
    non-ASCII, so a misconfigured pinned secret must fail closed, not 500."""
    app = create_app(test_config={session_auth.CONFIG_SECRET: "sécret-token"})
    with app.test_client() as client:
        resp = client.get("/api/health", headers={"User-Agent": _WEBVIEW_UA_WITH_TOKEN})

    assert resp.status_code == 200
    assert resp.headers["X-Frame-Options"] == "DENY"
    script_src = _directive(resp.headers["Content-Security-Policy"], "script-src")
    assert script_src is not None
    assert "'unsafe-eval'" not in script_src, "a non-ASCII expected token must fail closed"


def test_non_ascii_ua_token_extractor_returns_none():
    """The guard lives in the extractor, so _is_trusted_webview's
    compare_digest never sees a non-ASCII str."""
    ua = f"QuodeqDesktop/1.0 {WEBVIEW_TOKEN_UA_PREFIX}café Safari"
    assert session_auth._webview_token_from_ua(ua) is None
    ascii_ua = f"QuodeqDesktop/1.0 {WEBVIEW_TOKEN_UA_PREFIX}abc123 Safari"
    assert session_auth._webview_token_from_ua(ascii_ua) == "abc123"


def test_audit_log_records_final_status_for_non_ascii_ua(monkeypatch):
    """The after_request audit line runs ahead of the CSP build, so once the
    TypeError is gone it logs the request's real final status code."""
    from unittest.mock import patch

    hostile_ua = f"QuodeqDesktop/1.0 {WEBVIEW_TOKEN_UA_PREFIX}tøken"
    app = create_app()
    with patch.object(security._logger, "info") as info, app.test_client() as client:
        resp = client.get("/api/health", headers={"User-Agent": hostile_ua})

    assert resp.status_code == 200
    audit_calls = [c.args for c in info.call_args_list if c.args and c.args[0].startswith("API: ")]
    assert audit_calls, "after_request must emit an audit line"
    assert audit_calls[-1][2] == "/api/health"
    assert audit_calls[-1][4] == 200, "the audit line must carry the real final status code"


def test_is_trusted_webview_compares_against_the_given_secret():
    assert session_auth.is_trusted_webview(_WEBVIEW_UA_WITH_TOKEN, _TOKEN) is True
    assert session_auth.is_trusted_webview(_WEBVIEW_UA_WITH_TOKEN, "other") is False
    assert session_auth.is_trusted_webview(_WEBVIEW_UA_WITH_TOKEN, None) is False
