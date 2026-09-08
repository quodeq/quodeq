"""Per-launch shared secret gating the webview's CSP unsafe-eval relaxation."""
from __future__ import annotations

import logging
import secrets

# Env var read by quodeq.api.security to gate the webview-only CSP
# relaxation. Must match quodeq.api.security._ENV_WEBVIEW_TOKEN.
_ENV_WEBVIEW_TOKEN = "QUODEQ_WEBVIEW_TOKEN"

_webview_token: str | None = None


def _get_webview_token() -> str:
    """Return this process's launch token, generating it on first use.

    Memoized so the API subprocess (started via _ensure_action_api[_forced],
    which sets it into this process's environment before spawning) and the
    webview subprocess (started later by _serve_native, which appends it to
    argv) get the same value, however far apart their call sites are.
    """
    global _webview_token
    if _webview_token is None:
        _webview_token = secrets.token_urlsafe(24)
    return _webview_token


def _warn_reused_api_token_mismatch(base_url: str) -> None:
    """Explain why the desktop shell's CSP relaxation will not be granted.

    The token is only handed to an API process we spawn ourselves. A reused
    API (a second `quodeq dashboard`, or an API started separately) keeps
    whatever token it launched with while the webview we are about to open
    gets this launch's fresh one, so _is_trusted_webview fails closed. That
    is correct, but it silently breaks pywebview's new Function() JS bridge,
    which is baffling without this line.
    """
    logging.getLogger(__name__).warning(
        "Reusing the Action API already running at %s; it was started with a "
        "different (or no) webview launch token, so the native window's CSP "
        "'unsafe-eval' relaxation will not be granted and its JS bridge may "
        "not work. Stop that API and relaunch to pair them.", base_url,
    )
