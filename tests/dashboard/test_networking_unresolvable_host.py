"""An unresolvable host fails the port scan with a RuntimeError naming the host."""
from __future__ import annotations

import socket

import pytest

from quodeq.dashboard.runner import choose_ui_port

_BAD_HOST = "no-such-host.invalid"
_START_PORT = 8765


class _UnresolvableSocket:
    def __init__(self, *_args):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def settimeout(self, _timeout):
        pass

    def connect_ex(self, _address):
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")


def test_choose_ui_port_names_an_unresolvable_host(monkeypatch):
    monkeypatch.setattr(socket, "socket", _UnresolvableSocket)
    with pytest.raises(RuntimeError, match=_BAD_HOST) as excinfo:
        choose_ui_port(_START_PORT, host=_BAD_HOST)
    assert isinstance(excinfo.value.__cause__, socket.gaierror)
