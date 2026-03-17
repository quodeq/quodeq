"""Shared SSRF protection: detect private/loopback/link-local addresses."""
from __future__ import annotations

import ipaddress
import socket
from functools import lru_cache


@lru_cache(maxsize=256)
def is_private_address(hostname: str) -> bool:
    """Return True if *hostname* resolves to a private/loopback/link-local address (cached)."""
    if hostname in ("localhost", "localhost.localdomain"):
        return True
    try:
        addr = ipaddress.ip_address(hostname)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        pass
    try:
        for _fam, _typ, _pro, _can, sockaddr in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(sockaddr[0])
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                return True
    except (socket.gaierror, OSError):
        pass
    return False
