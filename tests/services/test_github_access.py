"""The ladder: ambient git, stored token, gh token, else needs sign-in."""
from __future__ import annotations

import base64

from quodeq.config.github_account import GitHubAccount, TokenMethod
from quodeq.data.fs.git_access_probe import ProbeResult
from quodeq.services.github_access import (
    AccessCache, AccessDeps, AccessMethod, access_env, cache_key, https_form, is_github_host,
    remote_host, resolve_access,
)
from quodeq.services.github_gh_cli import GhStatus
from quodeq.shared.git_errors import GitFailureKind

_GH_URL = "https://github.com/o/r.git"
_OTHER_URL = "https://gitlab.example.com/o/r.git"
_ACCT = GitHubAccount(token="gho_stored", login="v", method=TokenMethod.PASTED)
_NOT_FOUND = ProbeResult(GitFailureKind.NOT_FOUND, "remote: Repository not found.")
_OK = ProbeResult(GitFailureKind.OK)


class _Probe:
    """Answers per token seen in the env; records every call."""

    def __init__(self, by_token: dict[str | None, ProbeResult]):
        self.by_token = by_token
        self.calls: list[str | None] = []

    def __call__(self, url, *, env=None, **_):
        token = _token_in(env)
        self.calls.append(token)
        return self.by_token[token]


def _token_in(env):
    header = (env or {}).get("GIT_CONFIG_VALUE_0")
    if not header:
        return None
    raw = base64.b64decode(header.split(" ", 2)[2]).decode()
    return raw.split(":", 1)[1]


def _deps(probe, account=None, gh=GhStatus(False, False)):
    return AccessDeps(probe=probe, load_account=lambda: account, gh=lambda **_: gh, env={})


def test_remote_host_and_github_detection():
    assert remote_host("git@github.com:o/r.git") == "github.com"
    assert remote_host("ssh://git@github.com/o/r.git") == "github.com"
    assert remote_host(_OTHER_URL) == "gitlab.example.com"
    assert is_github_host("github.com") and is_github_host("GitHub.com")
    assert not is_github_host("gitlab.example.com")


def test_access_env_is_host_scoped_basic_auth_in_env_only():
    env = access_env("tok", base={"PATH": "/x"})
    assert env["PATH"] == "/x"
    assert env["GIT_CONFIG_COUNT"] == "1"
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraHeader"
    expected = base64.b64encode(b"x-access-token:tok").decode()
    assert env["GIT_CONFIG_VALUE_0"] == f"Authorization: Basic {expected}"
    assert "tok" not in env["GIT_CONFIG_VALUE_0"]


def test_ambient_ok_never_consults_a_token():
    probe = _Probe({None: _OK})
    result = resolve_access(_GH_URL, deps=_deps(probe, account=_ACCT), cache=AccessCache())
    assert result.reachable and result.method is AccessMethod.AMBIENT and result.env is None
    assert probe.calls == [None]


def test_stored_token_wins_after_ambient_fails():
    probe = _Probe({None: _NOT_FOUND, "gho_stored": _OK})
    result = resolve_access(_GH_URL, deps=_deps(probe, account=_ACCT), cache=AccessCache())
    assert result.method is AccessMethod.QUODEQ
    assert _token_in(result.env) == "gho_stored"


def test_dead_stored_token_falls_through_to_gh():
    probe = _Probe({None: _NOT_FOUND, "gho_stored": ProbeResult(GitFailureKind.AUTH_REQUIRED, "bad"), "gho_gh": _OK})
    deps = _deps(probe, account=_ACCT, gh=GhStatus(True, True, "gho_gh"))
    result = resolve_access(_GH_URL, deps=deps, cache=AccessCache())
    assert result.method is AccessMethod.GH
    assert probe.calls == [None, "gho_stored", "gho_gh"]


def test_nothing_works_reports_the_ambient_reason():
    probe = _Probe({None: _NOT_FOUND, "gho_gh": _NOT_FOUND})
    result = resolve_access(_GH_URL, deps=_deps(probe, gh=GhStatus(True, True, "gho_gh")), cache=AccessCache())
    assert not result.reachable
    assert result.method is AccessMethod.NONE
    assert result.kind is GitFailureKind.NOT_FOUND
    assert result.detail == "remote: Repository not found."
    assert result.is_github and result.host == "github.com"


def test_non_sign_in_kind_stops_at_rung_one():
    probe = _Probe({None: ProbeResult(GitFailureKind.HOST_KEY, "Host key verification failed.")})
    result = resolve_access("git@github.com:o/r.git", deps=_deps(probe, account=_ACCT), cache=AccessCache())
    assert result.kind is GitFailureKind.HOST_KEY and probe.calls == [None]


def test_non_github_host_stops_at_rung_one():
    probe = _Probe({None: ProbeResult(GitFailureKind.AUTH_REQUIRED, "denied")})
    result = resolve_access(_OTHER_URL, deps=_deps(probe, account=_ACCT), cache=AccessCache())
    assert not result.reachable and not result.is_github and probe.calls == [None]


def test_cache_is_per_repository_and_forget_restores_probing():
    probe = _Probe({None: _NOT_FOUND, "gho_stored": _OK})
    cache = AccessCache()
    first = resolve_access(_GH_URL, deps=_deps(probe, account=_ACCT), cache=cache)
    again = resolve_access(_GH_URL, deps=_deps(probe, account=_ACCT), cache=cache)
    assert again.method is first.method is AccessMethod.QUODEQ
    assert again.clone_url == first.clone_url
    assert probe.calls == [None, "gho_stored"]  # second call never probed
    resolve_access("https://github.com/other/repo.git", deps=_deps(probe, account=_ACCT), cache=cache)
    assert len(probe.calls) == 4  # a different repo on the same host probes again
    cache.forget(cache_key(_GH_URL))
    resolve_access(_GH_URL, deps=_deps(probe, account=_ACCT), cache=cache)
    assert len(probe.calls) == 6


def test_https_form_maps_scp_and_ssh_and_keeps_https():
    assert https_form("git@github.com:o/r.git") == _GH_URL
    assert https_form("ssh://git@github.com/o/r.git") == _GH_URL
    assert https_form(_GH_URL) == _GH_URL


def test_scp_url_token_rung_probes_and_clones_over_https():
    seen: list[str] = []

    def probe(url, *, env=None, **_):
        seen.append(url)
        return _OK if _token_in(env) == "gho_stored" else _NOT_FOUND

    result = resolve_access("git@github.com:o/r.git", deps=_deps(probe, account=_ACCT), cache=AccessCache())
    assert result.method is AccessMethod.QUODEQ
    assert result.clone_url == _GH_URL
    assert seen == ["git@github.com:o/r.git", _GH_URL]


def test_https_token_result_clone_url_is_the_url_and_ambient_has_none():
    probe = _Probe({None: _NOT_FOUND, "gho_stored": _OK})
    token = resolve_access(_GH_URL, deps=_deps(probe, account=_ACCT), cache=AccessCache())
    assert token.clone_url == _GH_URL
    ambient = resolve_access(_GH_URL, deps=_deps(_Probe({None: _OK})), cache=AccessCache())
    assert ambient.clone_url is None
