"""The ladder's URL guard, DNS pin, host parsing, refresh env and repr safety."""
from __future__ import annotations

import pytest

from quodeq.config.github_account import GitHubAccount, TokenMethod
from quodeq.data.fs.git_access_probe import ProbeResult
from quodeq.services import github_access
from quodeq.services.github_access import (
    AccessCache, AccessDeps, AccessMethod, AccessResult, cache_key, cached_access_env, https_form,
    is_github_host, refresh_access_env, remote_host, resolve_access,
)
from quodeq.services.github_gh_cli import GhStatus
from quodeq.shared.git_errors import GitFailureKind

_OK = ProbeResult(GitFailureKind.OK)
_PIN = ["http.curloptResolve=github.com:443:140.82.121.3"]


class _Recorder:
    def __init__(self, answer=_OK):
        self.answer = answer
        self.calls: list[tuple[str, tuple]] = []

    def __call__(self, url, *, env=None, git_config=(), **_):
        self.calls.append((url, tuple(git_config)))
        return self.answer


def _deps(probe, pin=lambda url: list(_PIN), account=None):
    return AccessDeps(probe=probe, load_account=lambda: account, gh=lambda **_: GhStatus(False, False), env={}, pin=pin)


@pytest.mark.parametrize("url", [
    "https://127.0.0.1/x.git", "https://169.254.169.254/latest/meta", "http://github.com/o/r.git", "not a url",
])
def test_rejected_urls_answer_invalid_url_without_probing(url, monkeypatch):
    monkeypatch.setattr("quodeq.data.fs.repo_validation._resolves_to_private", lambda host: False)
    probe = _Recorder()
    result = resolve_access(url, deps=_deps(probe), cache=AccessCache())
    assert result.kind is GitFailureKind.INVALID_URL
    assert not result.reachable and result.method is AccessMethod.NONE and not result.is_github
    assert probe.calls == []


def test_ssh_host_resolving_private_is_invalid_url(monkeypatch):
    monkeypatch.setattr("quodeq.data.fs.repo_validation._resolves_to_private", lambda host: True)
    probe = _Recorder()
    result = resolve_access("git@internal.example.com:o/r.git", deps=_deps(probe), cache=AccessCache())
    assert result.kind is GitFailureKind.INVALID_URL and probe.calls == []


def test_pin_reaches_every_probe_in_the_call(monkeypatch):
    monkeypatch.setattr("quodeq.data.fs.repo_validation._resolves_to_private", lambda host: False)
    probe = _Recorder(ProbeResult(GitFailureKind.NOT_FOUND))
    pins: list[str] = []

    def pin(url):
        pins.append(url)
        return list(_PIN)

    acct = GitHubAccount(token="t", login="v", method=TokenMethod.PASTED)
    resolve_access("https://github.com/o/r.git", deps=_deps(probe, pin=pin, account=acct), cache=AccessCache())
    assert pins == ["https://github.com/o/r.git"]  # computed once
    assert [cfg for _url, cfg in probe.calls] == [tuple(_PIN), tuple(_PIN)]


def test_unpinnable_host_is_network_without_probing(monkeypatch):
    monkeypatch.setattr("quodeq.data.fs.repo_validation._resolves_to_private", lambda host: False)
    probe = _Recorder()

    def pin(url):
        raise ValueError("github.com resolves to a private/internal address")

    result = resolve_access("https://github.com/o/r.git", deps=_deps(probe, pin=pin), cache=AccessCache())
    assert result.kind is GitFailureKind.NETWORK and probe.calls == []


def test_digit_leading_owner_and_ssh_port_parse_to_the_real_host():
    assert remote_host("git@github.com:1password/cli.git") == "github.com"
    assert is_github_host(remote_host("git@github.com:1password/cli.git"))
    assert https_form("git@github.com:1password/cli.git") == "https://github.com/1password/cli.git"
    assert remote_host("ssh://git@github.com:22/org/repo.git") == "github.com"
    assert https_form("ssh://git@github.com:22/org/repo.git") == "https://github.com/org/repo.git"
    assert remote_host("https://GitHub.com/o/r.git") == "github.com"
    assert cache_key("git@github.com:1password/cli.git") == cache_key("https://github.com/1password/cli.git")
    assert cache_key("git@github.com:1password/cli.git") == "github.com/1password/cli"


def test_cached_access_env_and_refresh_walks_once(monkeypatch):
    cache = AccessCache()
    monkeypatch.setattr(github_access, "_default_cache", cache)
    url = "https://github.com/o/r.git"
    walks: list[str] = []

    def fake_resolve(u):
        walks.append(u)
        return AccessResult(False, AccessMethod.NONE, GitFailureKind.NOT_FOUND, "", "github.com", True, None)

    monkeypatch.setattr(github_access, "resolve_access", fake_resolve)
    assert cached_access_env(url) is None
    assert refresh_access_env(url) is None and refresh_access_env(url) is None
    assert walks == [url]  # a miss walks the ladder once per process
    cache.put(cache_key(url), AccessMethod.QUODEQ, {"GIT_CONFIG_VALUE_0": "x"}, url)
    assert cached_access_env(url) == {"GIT_CONFIG_VALUE_0": "x"}
    assert refresh_access_env(url) == {"GIT_CONFIG_VALUE_0": "x"}
    assert walks == [url]


def test_access_result_repr_hides_the_env():
    result = AccessResult(True, AccessMethod.QUODEQ, GitFailureKind.OK, "", "github.com", True, {"GIT_CONFIG_VALUE_0": "x"})
    assert "GIT_CONFIG_VALUE_0" not in repr(result)
    cache = AccessCache()
    cache.put("k", AccessMethod.QUODEQ, {"GIT_CONFIG_VALUE_0": "x"})
    assert "GIT_CONFIG_VALUE_0" not in repr(cache.get("k"))
