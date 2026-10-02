"""gh_status never raises: absent, logged out, logged in, or hanging gh."""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

from quodeq.services.github_gh_cli import GH_TOKEN_TIMEOUT_S, GhStatus, gh_status


def test_gh_absent():
    assert gh_status(env={}, which=lambda name, path=None: None) == GhStatus(False, False)


def test_gh_logged_out_has_text_on_stderr_and_nonzero_exit():
    def run(argv, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="You are not logged into any GitHub hosts.")
    assert gh_status(env={}, which=lambda n, path=None: "/usr/local/bin/gh", run=run) == GhStatus(True, False)


def test_gh_logged_in_returns_the_token():
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="gho_abc\n", stderr="")
    status = gh_status(env={"PATH": "/x"}, which=lambda n, path=None: "/x/gh", run=run)
    assert status == GhStatus(True, True, "gho_abc")
    argv, kwargs = calls[0]
    assert argv == ["/x/gh", "auth", "token"]
    assert kwargs["timeout"] == GH_TOKEN_TIMEOUT_S
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["env"] == {"PATH": "/x"}


def test_gh_timeout_or_oserror_is_logged_out():
    def hang(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=5)
    assert gh_status(env={}, which=lambda n, path=None: "/x/gh", run=hang) == GhStatus(True, False)

    def broken(argv, **kwargs):
        raise OSError("exec failed")
    assert gh_status(env={}, which=lambda n, path=None: "/x/gh", run=broken) == GhStatus(True, False)


def test_empty_token_is_logged_out():
    def run(argv, **kwargs):
        return SimpleNamespace(returncode=0, stdout="\n", stderr="")
    assert gh_status(env={}, which=lambda n, path=None: "/x/gh", run=run) == GhStatus(True, False)


def test_repr_never_shows_the_token():
    assert "gho_gh" not in repr(GhStatus(True, True, "gho_gh"))
