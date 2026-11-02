"""Shared SSRF protection: detect private/loopback/link-local addresses.

Nothing here is cached: a verdict is only good for the DNS answer it was
computed from, and a rebinding host changes its answer between one lookup
and the next. Callers that need the same answer twice (check, then connect)
take the addresses from :func:`resolve_addresses` and pin them.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from collections.abc import Callable

from quodeq.shared.constants import LOCALHOST, LOCALHOST_LOCALDOMAIN

_logger = logging.getLogger(__name__)

_IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def is_internal_ip(address: str) -> bool:
    """True when *address* (an IP string) is not a public unicast address.

    An IPv4-mapped IPv6 address (``::ffff:127.0.0.1``) is judged as the IPv4
    address it carries. Unspecified (``0.0.0.0`` reaches this host on most
    stacks), multicast and reserved ranges count as internal too.
    """
    addr: _IPAddress = ipaddress.ip_address(address)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return (addr.is_private or addr.is_loopback or addr.is_link_local
            or addr.is_unspecified or addr.is_multicast or addr.is_reserved)


def _ip_literal(hostname: str) -> _IPAddress | None:
    """*hostname* as an IP address when it is one, in any spelling git accepts."""
    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        _logger.debug("Cannot parse %r as IP literal, falling through to DNS", hostname)
    # git/libc accept IPv4 literals in octal/hex/dword/short forms that
    # ``ipaddress`` rejects (e.g. 0177.0.0.1, 0x7f000001, 2130706433, 127.1).
    # Canonicalize the way git's resolver will so SSRF via alternate IPv4
    # encodings is caught here instead of slipping through to a public-looking
    # DNS answer. inet_aton raises OSError for real hostnames -> DNS fallback.
    try:
        return ipaddress.ip_address(socket.inet_ntoa(socket.inet_aton(hostname)))
    except OSError as exc:
        _logger.debug("%r is not an IPv4 literal (%s), falling through to DNS", hostname, exc)
    return None


def resolve_addresses(hostname: str) -> tuple[str, ...]:
    """Every address *hostname* stands for right now, as strings; empty when
    it does not resolve. A literal resolves to itself."""
    literal = _ip_literal(hostname)
    if literal is not None:
        return (str(literal),)
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, OSError) as exc:
        _logger.warning("DNS resolution failed for %r: %s", hostname, exc)
        return ()
    return tuple(dict.fromkeys(str(sockaddr[0]) for _fam, _typ, _pro, _can, sockaddr in infos))


def is_private_address(hostname: str) -> bool:
    """Return True if *hostname* resolves to a private/loopback/link-local address.

    Fails closed: a name that does not resolve counts as private.
    """
    if hostname in (LOCALHOST, LOCALHOST_LOCALDOMAIN):
        return True
    addresses = resolve_addresses(hostname)
    if not addresses:
        return True
    return any(is_internal_ip(a) for a in addresses)


def public_addresses(
    hostname: str, *, resolve: Callable[[str], tuple[str, ...]] = resolve_addresses,
) -> tuple[str, ...]:
    """Resolve *hostname* once and return that answer, for the caller to pin.

    Raises ``ValueError`` when it does not resolve or any address is
    internal. Connecting to these addresses (not to the name again) is what
    closes the DNS-rebinding window between the check and the connect.
    """
    addresses = resolve(hostname)
    if not addresses:
        raise ValueError(f"could not resolve {hostname}")
    if any(is_internal_ip(a) for a in addresses):
        raise ValueError(f"{hostname} resolves to a private/internal address")
    return addresses


def is_loopback_address(hostname: str) -> bool:
    """Return True if *hostname* is a loopback address (127.x.x.x or ::1) or 'localhost'.

    Resolves through :func:`resolve_addresses`, so it reads encoded IPv4
    literals exactly as :func:`is_private_address` does. A name that does
    not resolve is not loopback.
    """
    if hostname in (LOCALHOST, LOCALHOST_LOCALDOMAIN):
        return True
    addresses = resolve_addresses(hostname)
    return bool(addresses) and all(ipaddress.ip_address(a).is_loopback for a in addresses)
