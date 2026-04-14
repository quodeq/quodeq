"""Repository URL validation and SSRF protection."""

from __future__ import annotations

import re

from quodeq.shared.ssrf import is_private_address

_REPO_URL_RE = re.compile(
    r"^(https?://[\w.\-]+/[\w.\-/]+(\.git)?|git@[\w.\-]+:[\w.\-/]+(\.git)?)$"
)

# IP-like hostnames that must be rejected to prevent SSRF via git clone.
# Covers IPv4 private ranges, IPv6 loopback (::1), IPv6 ULA (fc00::/7), and localhost.
_PRIVATE_HOST_RE = re.compile(
    r"^https?://"
    r"(10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+|169\.254\.\d+\.\d+|127\.\d+\.\d+\.\d+"
    r"|localhost"
    r"|\[::1\]|\[fc[0-9a-fA-F]{2}:.*\]|\[fd[0-9a-fA-F]{2}:.*\]|\[fe80:.*\]"
    r")[:/]"
)


def _resolves_to_private(hostname: str) -> bool:
    """Return True if *hostname* resolves to a private/loopback IP address.

    Delegates to the shared SSRF module to avoid duplicating DNS-resolution
    and private-address detection logic.
    """
    return is_private_address(hostname)


def is_valid_repo_url(url: str) -> bool:
    """Return True if *url* matches the expected git repository URL format."""
    return _REPO_URL_RE.match(url) is not None
