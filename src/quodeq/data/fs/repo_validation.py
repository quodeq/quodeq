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


def _remote_host(repo_input: str) -> str:
    """Return the host of a format-validated repo URL.

    Handles both supported forms so the private-host check covers them equally:
    ``https://host/path`` and the scp-like ``git@host:path`` (SSH) form. The
    SSH form skips ``_PRIVATE_HOST_RE`` (anchored to ``^https?://``), so without
    this it would reach git clone unguarded.
    """
    if repo_input.startswith("http"):
        import urllib.parse
        return urllib.parse.urlparse(repo_input).hostname or ""
    if repo_input.startswith("git@"):
        return repo_input[len("git@"):].split(":", 1)[0].strip("[]")
    return ""


def is_valid_repo_url(url: str) -> bool:
    """Return True if *url* matches the expected git repository URL format."""
    return _REPO_URL_RE.match(url) is not None


def validate_remote_url(repo_input: str) -> None:
    """Reject malformed / private / DNS-rebinding repository URLs.

    Shared SSRF guard used by both the CLI clone path
    (:func:`quodeq.data.fs.repo_clone.prepare_repository`) and the web API
    registration path (:func:`quodeq.services.evaluation_mixin._register_project`),
    so the two entry points cannot drift apart on what they consider safe.
    Raises ``ValueError`` for any rejected URL.
    """
    if not _REPO_URL_RE.match(repo_input):
        raise ValueError(f"Invalid repository URL format: {repo_input}. Expected: https://github.com/user/repo or git@github.com:user/repo.git")
    if _PRIVATE_HOST_RE.match(repo_input):
        raise ValueError("Repository URLs pointing to private/internal addresses are not allowed")
    hostname = _remote_host(repo_input)
    if hostname and _resolves_to_private(hostname):
        raise ValueError("Repository URL resolves to a private/internal address")
