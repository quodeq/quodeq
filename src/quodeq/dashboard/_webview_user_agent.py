"""The user-agent the native window sends, and the version it carries.

Kept apart from the macOS app identity it used to sit beside: the CSP
relaxation in ``quodeq.api.security`` is keyed off these two strings, so they
are a cross-process contract rather than a window detail. ``security.py``
carries its own copies, and tests/dashboard/test_native_chrome.py pins that
the two agree.
"""
from __future__ import annotations


def quodeq_version() -> str:
    """The installed quodeq version, or "dev" when the metadata is missing."""
    try:
        from importlib.metadata import PackageNotFoundError, version  # noqa: PLC0415
        return version("quodeq")
    except PackageNotFoundError:  # metadata may be missing in dev
        return "dev"


# Human-readable marker (must match quodeq.api.security._WEBVIEW_UA_MARKER).
# Not itself a security check — any HTTP client can send this substring; the
# CSP relaxation is gated on the per-launch token below.
WEBVIEW_UA_MARKER = "QuodeqDesktop"

# UA prefix ahead of the token (must match security._WEBVIEW_TOKEN_UA_PREFIX).
WEBVIEW_TOKEN_UA_PREFIX = "QuodeqWebviewToken/"


def webview_user_agent(token: str | None = None) -> str:
    """UA carrying the marker (human-readable) and the token that actually
    grants the relaxed CSP (see quodeq.api.security._is_trusted_webview)."""
    token_part = f" {WEBVIEW_TOKEN_UA_PREFIX}{token}" if token else ""
    return (
        "Mozilla/5.0 (quodeq) AppleWebKit/605.1.15 (KHTML, like Gecko) "
        f"{WEBVIEW_UA_MARKER}/{quodeq_version()}{token_part} Safari/605.1.15"
    )
