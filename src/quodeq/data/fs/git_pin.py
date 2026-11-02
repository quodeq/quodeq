"""DNS pinning for git's own network connections (``http.curloptResolve``).

A URL is validated against the private-address policy before git runs, but
git does its own DNS lookup, and a rebinding host can answer that second
lookup with an internal address. Resolving once here, judging that answer,
and handing the same addresses to git closes the gap for http(s) remotes.
Shared by the clone (services/_fs_clone.py) and the reachability probe
(services/github_access.py).
"""
from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlparse

from quodeq.shared.constants import SCHEME_HTTP, SCHEME_HTTPS
from quodeq.shared.ssrf import public_addresses, resolve_addresses

_DEFAULT_PORTS = {SCHEME_HTTP: 80, SCHEME_HTTPS: 443}


def pinned_git_config(
    url: str, *, resolve: Callable[[str], tuple[str, ...]] = resolve_addresses,
) -> list[str]:
    """``http.curloptResolve`` entries pinning git to the addresses *url*'s
    host resolves to right now.

    Other schemes (scp-like ``git@host:``, ``ssh://``) cannot be pinned and
    get no entry. Raises ``ValueError`` when the host does not resolve or
    resolves to a private/internal address.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if parsed.scheme not in _DEFAULT_PORTS or not hostname:
        return []
    addresses = public_addresses(hostname, resolve=resolve)
    port = parsed.port or _DEFAULT_PORTS[parsed.scheme]
    return [f"http.curloptResolve={hostname}:{port}:{','.join(addresses)}"]

