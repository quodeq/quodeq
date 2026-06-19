"""URL validation helpers for SSRF prevention."""
from __future__ import annotations

from urllib.parse import urlparse

from quodeq.shared.ssrf import is_loopback_address, is_private_address


def validate_url_safe(
    url: str,
    *,
    allow_private: bool = False,
    allow_loopback: bool = False,
) -> None:
    """Raise ``ValueError`` if *url* uses a non-HTTP scheme or targets a private address.

    Only ``http://`` and ``https://`` schemes are allowed.  The hostname is
    resolved and checked against private/loopback/link-local ranges via
    :func:`~quodeq.shared.ssrf.is_private_address`.

    Set *allow_private* to ``True`` for endpoints that are intentionally on a
    local network (e.g. self-hosted Ollama or LLM servers on a LAN).  This
    still enforces the scheme allowlist but skips the private-IP check.

    Set *allow_loopback* to ``True`` to allow loopback addresses (``127.x.x.x``,
    ``::1``, ``localhost``) while still blocking other private ranges such as
    ``10.x.x.x``, ``192.168.x.x``, and link-local/metadata addresses
    (``169.254.x.x``).  Use this for services that are intentionally local-only
    (e.g. omlx running on localhost) without opening up the full private range.
    *allow_loopback* is ignored when *allow_private* is ``True``.
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
        if allow_loopback and is_loopback_address(hostname):
            return  # loopback is explicitly permitted
        raise ValueError(f"URL targets a private/internal address: {hostname!r}")
