"""Hand the desktop window the local API's session secret, over stdin.

The API mints the secret and publishes it in its 0600 session file
(quodeq.shared.api_session); the launcher reads it there and passes it on.
The window puts it in its User-Agent, which is how every request it makes,
navigations included, proves it is the Quodeq UI (quodeq.api.session_auth)
and wins the CSP 'unsafe-eval' its JS bridge needs.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import typing
from pathlib import Path

from quodeq.shared.api_session import secret_for_url

_logger = logging.getLogger(__name__)


def window_token(base_url: str) -> str:
    """The secret for the API at *base_url*, or "" (with a warning) when it published none.

    An API from a Quodeq version before session auth writes no file; its
    window then runs token-less and that API serves it the strict CSP.
    """
    token = secret_for_url(base_url)
    if not token:
        _logger.warning(
            "The Action API at %s published no session secret, so the window cannot "
            "authenticate to it. Stop that API and relaunch to pair them.", base_url,
        )
    return token or ""


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


def _send_token(window_proc: subprocess.Popen | None, token: str) -> None:
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
        stdin.write(f"{token}\n".encode())
        stdin.flush()
    except (OSError, ValueError) as exc:
        _logger.debug("webview token handoff failed: %s", exc)
    finally:
        # Must close even when the write failed: the child blocks in
        # readline() until this end is closed.
        try:
            stdin.close()
        except (OSError, ValueError) as exc:
            _logger.debug("webview token stdin close failed: %s", exc)


def spawn_window_with_token(
    spawn: typing.Callable[..., subprocess.Popen], cmd: list[str], *, stderr: typing.Any, token: str,
) -> subprocess.Popen:
    """Spawn the webview window and hand it the token over stdin, never argv.

    argv is world-readable: /proc/<pid>/cmdline is mode 0444 and `ps` shows it
    to every user on the machine, so a token passed there let any local user
    forge the UA that wins the CSP 'unsafe-eval' relaxation (see
    quodeq.api.session_auth for what that grants). A pipe is
    visible only to the two processes holding it.
    """
    window_proc = spawn(
        cmd,
        start_new_session=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=stderr,
    )
    _send_token(window_proc, token)
    return window_proc


def open_webview_log():
    """Where the window's stderr goes: ``~/.quodeq/run/webview.log``, or DEVNULL if unwritable.

    A log file, not DEVNULL, so a platform import failure or GTK error is
    actually recoverable.
    """
    webview_log_path = Path.home() / ".quodeq" / "run" / "webview.log"
    try:
        webview_log_path.parent.mkdir(parents=True, exist_ok=True)
        return webview_log_path.open("a", encoding="utf-8")
    except OSError:
        return subprocess.DEVNULL
