"""The environment an agent CLI inherits: connectivity, never credentials."""
from __future__ import annotations

import pytest

from quodeq.shared.child_env import allowlisted_env

# The settings the OS sandbox opens a loopback port for (shared/os_sandbox.py).
PROXY_KEYS = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy")


@pytest.mark.parametrize("key", PROXY_KEYS)
def test_every_proxy_setting_the_sandbox_reads_reaches_the_cli(key):
    """A SOCKS-only setup (ALL_PROXY) must not lose its proxy on the way to the agent."""
    assert allowlisted_env({key: "socks5://127.0.0.1:1080"}) == {key: "socks5://127.0.0.1:1080"}


def test_credentials_stay_behind():
    env = allowlisted_env({"PATH": "/bin", "GH_TOKEN": "x", "AWS_SECRET_ACCESS_KEY": "y"})
    assert env == {"PATH": "/bin"}
