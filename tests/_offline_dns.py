"""Autouse: the SSRF guard's name lookups are answered offline.

``quodeq.shared.ssrf`` resolves a hostname to decide whether a URL is public,
and it fails closed: no answer, or a private one, means "refuse". Tests that
pass ``https://example.com`` or a GitHub URL through that guard therefore
depended on the runner's resolver, and failed together whenever it was down
or answered with a private address.

Only the guard's view of ``socket`` is replaced. Code that opens real
connections keeps the real resolver, and a test that patches
``socket.getaddrinfo`` itself keeps control of the answer.
"""
from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest

from quodeq.shared import ssrf

# What every resolvable name stands for in tests: one public unicast address.
PUBLIC_TEST_ADDRESS = "140.82.121.3"
# RFC 6761: names under .invalid never resolve.
_NEVER_RESOLVES = ".invalid"
_LOCALHOST = "localhost"

_real_getaddrinfo = socket.getaddrinfo


def _resolves(name: str) -> bool:
    """A dotted name resolves, as a public one would. A single label or a
    ``.invalid`` name does not, as on a resolver without search domains."""
    return "." in name.strip(".") and not name.rstrip(".").endswith(_NEVER_RESOLVES)


class _GuardSocket:
    """The ``socket`` module as ``quodeq.shared.ssrf`` sees it."""

    def getaddrinfo(self, host, port=None, *args, **kwargs):
        if socket.getaddrinfo is not _real_getaddrinfo or host == _LOCALHOST:
            # A test patched the resolver, or the name needs no network.
            return socket.getaddrinfo(host, port, *args, **kwargs)
        if not _resolves(str(host)):
            raise socket.gaierror(socket.EAI_NONAME, "offline test resolver: name does not resolve")
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (PUBLIC_TEST_ADDRESS, port or 0))]

    def __getattr__(self, name: str):
        return getattr(socket, name)


@pytest.fixture(autouse=True)
def _offline_dns(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep every test's SSRF checks off the runner's resolver."""
    monkeypatch.setattr(ssrf, "socket", _GuardSocket())
    yield
