"""Per-launch shared secret gating the webview's CSP unsafe-eval relaxation."""
from __future__ import annotations

import contextlib
import logging
import secrets
import subprocess
import sys
import typing

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


def read_token_from_stdin() -> str | None:
    """Child side: read this launch's token from stdin, where the parent's
    spawn_window_with_token wrote it.

    Returns None on anything unexpected (no stdin, empty line, closed pipe).
    The window then runs a token-less UA and the API serves it the strict
    CSP -- the JS bridge degrades, the security property holds.
    """
    try:
        if sys.stdin is None:
            return None
        return sys.stdin.readline().strip() or None
    except (OSError, ValueError):
        return None


def _send_token(window_proc: subprocess.Popen | None) -> None:
    """Write the launch token to the window's stdin, then close it.

    Best-effort by design: on any failure the child reads an empty line, gets
    no token, and the API serves it the strict CSP. Same fail-closed path as
    a wrong token, so a broken handover costs the JS bridge, never the
    security property.
    """
    stdin = getattr(window_proc, "stdin", None)
    if stdin is None:
        return
    try:
        stdin.write(f"{_get_webview_token()}\n".encode())
        stdin.flush()
    except (OSError, ValueError):
        pass
    finally:
        # Must close even when the write failed: the child blocks in
        # readline() until this end is closed.
        with contextlib.suppress(OSError, ValueError):
            stdin.close()


def spawn_window_with_token(
    spawn: typing.Callable[..., subprocess.Popen], cmd: list[str], *, stderr: typing.Any,
) -> subprocess.Popen:
    """Spawn the webview window and hand it the token over stdin, never argv.

    argv is world-readable: /proc/<pid>/cmdline is mode 0444 and `ps` shows it
    to every user on the machine, so a token passed there let any local user
    forge the UA that wins the CSP 'unsafe-eval' relaxation (see
    quodeq.api.security._is_trusted_webview for what that grants). A pipe is
    visible only to the two processes holding it.
    """
    window_proc = spawn(
        cmd,
        start_new_session=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=stderr,
    )
    _send_token(window_proc)
    return window_proc
