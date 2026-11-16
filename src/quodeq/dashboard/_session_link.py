"""Open the dashboard in a browser through a single-use launch link.

The API refuses a browser without its session cookie
(quodeq.api.session_auth). The launcher, which can read the API's session
file, asks for a short-lived code and opens ``/api/session/open?code=...``;
the API trades it for the cookie and redirects to the app. The code, unlike
the secret, is fine in argv and browser history: it works once, for two minutes.
"""
from __future__ import annotations

import json
import logging
import typing
import urllib.request

from quodeq.shared.api_session import SESSION_CODE_PATH, session_headers
from quodeq.shared.logging import log_info

_logger = logging.getLogger(__name__)

_TIMEOUT_S = 5.0


def launch_link(base_url: str) -> str | None:
    """A one-time link that signs this browser in to *base_url*, or None if the API would not issue one."""
    headers = session_headers(base_url)
    if not headers:
        return None
    try:
        req = urllib.request.Request(f"{base_url}{SESSION_CODE_PATH}", method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            path = json.loads(resp.read()).get("path")
    except (OSError, ValueError, AttributeError) as exc:
        _logger.warning("Could not get a launch link from %s: %s", base_url, exc)
        return None
    return f"{base_url}{path}" if isinstance(path, str) and path.startswith("/") else None


def open_in_browser(base_url: str, opener: typing.Callable[[str], object]) -> None:
    """Open the app at *base_url* signed in; falls back to the bare URL, which explains how to get in."""
    opener(launch_link(base_url) or base_url)


def log_launch_link(base_url: str) -> None:
    """For ``--no-open``: print a link the user can paste into a browser."""
    link = launch_link(base_url)
    if link:
        log_info(f"Open in a browser within two minutes: {link}")
