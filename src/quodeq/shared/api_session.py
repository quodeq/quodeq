"""The local API's per-launch session secret, and the file that hands it over.

The API mints the secret in memory at startup (``mint_session_secret``) and
refuses every ``/api`` request that does not carry it (see
``quodeq.api.session_auth``). Its own launcher, the desktop window and the
menubar read it from a user-private file in the run dir, keyed by port, so
the secret never travels through an environment variable (readable by any
same-user process via ``/proc/<pid>/environ`` or ``ps eww``) or argv.

The file lives in ``~/.quodeq/run``, never under a scanned repository or the
evaluations dir an analysis agent is pointed at.
"""
from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from quodeq.shared.env_paths import ensure_run_dir, run_dir_path

_logger = logging.getLogger(__name__)

SESSION_COOKIE = "quodeq_session"
SESSION_HEADER = "X-Quodeq-Session"
SESSION_OPEN_PATH = "/api/session/open"  # trades a launch code for the cookie
SESSION_CODE_PATH = "/api/session/code"  # issues a launch code to a caller holding the secret
# UA prefix the desktop window puts ahead of the secret (the window cannot
# set a cookie or header on its own navigations). Must match
# quodeq.dashboard._webview_user_agent.WEBVIEW_TOKEN_UA_PREFIX.
WEBVIEW_TOKEN_UA_PREFIX = "QuodeqWebviewToken/"

_SECRET_BYTES = 32
_FILE_MODE = 0o600


def mint_session_secret() -> str:
    """A fresh URL-safe secret; always ASCII, so compare_digest never raises on it."""
    return secrets.token_urlsafe(_SECRET_BYTES)


def session_file_path(port: int, env: dict[str, str] | None = None) -> Path:
    """Where the API on *port* publishes its secret."""
    return run_dir_path(env) / f"api-{port}.session"


def write_session_file(port: int, secret: str, env: dict[str, str] | None = None) -> Path:
    """Publish *secret* for *port*, readable by this user only.

    Written to a temp file created 0600 and renamed into place, so no reader
    ever sees a partial secret and no window exists where the file is
    world-readable.
    """
    target = session_file_path(port, env)
    ensure_run_dir(env)
    tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _FILE_MODE)
    try:
        with os.fdopen(fd, "w", encoding="ascii") as out:
            out.write(secret)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return target


def read_session_file(port: int, env: dict[str, str] | None = None) -> str | None:
    """The secret the API on *port* published, or None when there is none to read."""
    try:
        value = session_file_path(port, env).read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return value or None


def remove_session_file(port: int, secret: str, env: dict[str, str] | None = None) -> None:
    """Delete *port*'s file, but only while it still holds *secret*.

    A newer API on the same port may already have replaced it; that file is
    not this process's to remove.
    """
    if read_session_file(port, env) != secret:
        return
    try:
        session_file_path(port, env).unlink()
    except OSError as exc:
        _logger.debug("session file cleanup failed: %s", exc)


def secret_for_url(base_url: str, env: dict[str, str] | None = None) -> str | None:
    """The secret of the local API at *base_url*, read from its session file."""
    try:
        port = urlsplit(base_url).port
    except ValueError:
        return None
    return read_session_file(port, env) if port else None


def session_headers(base_url: str, env: dict[str, str] | None = None) -> dict[str, str]:
    """Headers that authenticate an in-machine caller (launcher, window, menubar) to *base_url*."""
    secret = secret_for_url(base_url, env)
    return {SESSION_HEADER: secret} if secret else {}
