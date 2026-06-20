"""Shared SSRF protection: detect private/loopback/link-local addresses."""
from __future__ import annotations

import ipaddress
import logging
import socket
from functools import lru_cache

_logger = logging.getLogger(__name__)

_LRU_CACHE_SIZE = 256


@lru_cache(maxsize=_LRU_CACHE_SIZE)
def is_private_address(hostname: str) -> bool:
    """Return True if *hostname* resolves to a private/loopback/link-local address (cached)."""
    if hostname in ("localhost", "localhost.localdomain"):
        return True
    try:
        addr = ipaddress.ip_address(hostname)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        _logger.debug("Cannot parse %r as IP literal, falling through to DNS", hostname)
    # git/libc accept IPv4 literals in octal/hex/dword/short forms that
    # ``ipaddress`` rejects (e.g. 0177.0.0.1, 0x7f000001, 2130706433, 127.1).
    # Canonicalize the way git's resolver will so SSRF via alternate IPv4
    # encodings is caught here instead of slipping through to a public-looking
    # DNS answer. inet_aton raises OSError for real hostnames -> DNS fallback.
    try:
        addr = ipaddress.ip_address(socket.inet_ntoa(socket.inet_aton(hostname)))
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except OSError:
        pass
    try:
        for _fam, _typ, _pro, _can, sockaddr in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(sockaddr[0])
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                return True
    except (socket.gaierror, OSError) as exc:
        _logger.warning("DNS resolution failed for %r - treating as private (fail-closed): %s", hostname, exc)
        return True
    return False


@lru_cache(maxsize=_LRU_CACHE_SIZE)
def is_loopback_address(hostname: str) -> bool:
    """Return True if *hostname* is a loopback address (127.x.x.x or ::1) or 'localhost'."""
    if hostname in ("localhost", "localhost.localdomain"):
        return True
    try:
        addr = ipaddress.ip_address(hostname)
        return bool(addr.is_loopback)
    except ValueError:
        _logger.debug("Cannot parse %r as IP literal, falling through to DNS", hostname)
    try:
        for _fam, _typ, _pro, _can, sockaddr in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(sockaddr[0])
            if not addr.is_loopback:
                return False
        return True
    except (socket.gaierror, OSError) as exc:
        _logger.warning("DNS resolution failed for %r - treating as private (fail-closed): %s", hostname, exc)
        return False
