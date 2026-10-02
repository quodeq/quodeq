"""pinned_git_config: resolve once, judge the answer, hand it to git."""
from __future__ import annotations

import pytest

from quodeq.data.fs.git_pin import pinned_git_config


def test_https_url_pins_host_port_and_addresses():
    pin = pinned_git_config("https://github.com/o/r.git", resolve=lambda host: ("140.82.121.3",))
    assert pin == ["http.curloptResolve=github.com:443:140.82.121.3"]


def test_ssh_forms_get_no_pin():
    assert pinned_git_config("git@github.com:o/r.git", resolve=lambda host: ()) == []
    assert pinned_git_config("ssh://git@github.com/o/r.git", resolve=lambda host: ()) == []


@pytest.mark.parametrize("answer", [(), ("10.0.0.1",), ("140.82.121.3", "127.0.0.1")])
def test_unresolvable_or_internal_host_raises(answer):
    with pytest.raises(ValueError):
        pinned_git_config("https://rebind.example.com/o/r.git", resolve=lambda host: answer)
