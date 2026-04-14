"""URL validation helpers for SSRF prevention."""
from __future__ import annotations

from urllib.parse import urlparse

from quodeq.shared.ssrf import is_private_address


def validate_url_safe(url: str, *, allow_private: bool = False) -> None:
    """Raise ``ValueError`` if *url* uses a non-HTTP scheme or targets a private address.

    Only ``http://`` and ``https://`` schemes are allowed.  The hostname is
    resolved and checked against private/loopback/link-local ranges via
    :func:`~quodeq.shared.ssrf.is_private_address`.

    Set *allow_private* to ``True`` for endpoints that are intentionally on a
    local network (e.g. self-hosted Ollama or LLM servers on a LAN).  This
    still enforces the scheme allowlist but skips the private-IP check.
    """
    if not url:
        raise ValueError("URL must not be empty")

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme {parsed.scheme!r} is not allowed; use http or https")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must include a hostname")

    if not allow_private and is_private_address(hostname):
        raise ValueError(f"URL targets a private/internal address: {hostname!r}")
