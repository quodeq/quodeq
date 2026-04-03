"""Networking helpers — host resolution, port scanning, and plaintext-HTTP guard."""
from __future__ import annotations

import logging
import os
import socket

from quodeq.shared.config_loader import get_default_host as _get_default_host

_DEFAULT_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})
_MAX_PORT_SCAN_TRIES = 20
_PORT_CHECK_TIMEOUT_S = 2
_MAX_PORT = 65535


def _local_hosts(
    env: dict[str, str] | None = None,
    defaults: frozenset[str] | None = None,
) -> frozenset[str]:
    extra = (env if env is not None else os.environ).get("QUODEQ_LOCAL_HOSTS", "")
    base = set(defaults or _DEFAULT_LOCAL_HOSTS)
    if extra:
        base.update(h.strip() for h in extra.split(",") if h.strip())
    return frozenset(base)


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(_PORT_CHECK_TIMEOUT_S)
        return sock.connect_ex((host, port)) == 0


def _choose_ui_port(start: int, host: str | None = None) -> int:
    host = host if host is not None else _get_default_host()
    port = start
    while _is_port_open(host, port):
        port += 1
        if port > _MAX_PORT:
            raise RuntimeError("No free port available.")
    return port


def _allow_plaintext_http(
    override: bool | None = None, env: dict[str, str] | None = None,
) -> bool:
    """Return True if plaintext HTTP to non-localhost is allowed."""
    if override is not None:
        return override
    return (env or os.environ).get("QUODEQ_ALLOW_PLAINTEXT_HTTP") == "1"
