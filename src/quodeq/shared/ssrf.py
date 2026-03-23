"""Shared SSRF protection: detect private/loopback/link-local addresses."""
from __future__ import annotations

import ipaddress
import logging
import socket
from functools import lru_cache

_logger = logging.getLogger(__name__)


@lru_cache(maxsize=256)
def is_private_address(hostname: str) -> bool:
    """Return True if *hostname* resolves to a private/loopback/link-local address (cached)."""
    if hostname in ("localhost", "localhost.localdomain"):
        return True
    try:
        addr = ipaddress.ip_address(hostname)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        _logger.debug("Cannot parse %r as IP literal, falling through to DNS", hostname)
    try:
        for _fam, _typ, _pro, _can, sockaddr in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(sockaddr[0])
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                return True
    except (socket.gaierror, OSError) as exc:
        _logger.warning("DNS resolution failed for %r — treating as private (fail-closed): %s", hostname, exc)
        return True
    return False
