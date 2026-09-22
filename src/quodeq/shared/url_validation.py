"""URL validation helpers for SSRF prevention."""
from __future__ import annotations

from urllib.parse import urlparse

from quodeq.shared.ssrf import is_loopback_address, is_private_address


def url_safety_error(
    url: str,
    *,
    allow_private: bool = False,
    allow_loopback: bool = False,
) -> str | None:
    """Return an error message if *url* uses a non-HTTP scheme or targets a
    private address, else None. Message text and branch order mirror
    :func:`validate_url_safe` exactly."""
    if not url:
        return "URL must not be empty"

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return f"URL scheme {parsed.scheme!r} is not allowed; use http or https"

    hostname = parsed.hostname
    if not hostname:
        return "URL must include a hostname"

    if not allow_private and is_private_address(hostname):
        if allow_loopback and is_loopback_address(hostname):
            return None  # loopback is explicitly permitted
        return f"URL targets a private/internal address: {hostname!r}"
    return None


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
    err = url_safety_error(url, allow_private=allow_private, allow_loopback=allow_loopback)
    if err is not None:
        raise ValueError(err)
