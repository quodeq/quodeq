"""The access ladder: how quodeq reaches a git remote, tried in order.

0. The URL itself: format, private/internal hosts (the SSRF guard) and the
   DNS pin are checked before any git process starts, so no caller can
   probe an address the clone would refuse.
1. Ambient git (SSH agent, credential helper): what `git clone` in a terminal
   would use. Most users never get past this rung.
2. The token quodeq stored (sign-in or paste).
3. The gh CLI's token.
4. Needs sign-in: the honest reason from rung 1, for the UI's access panel.

Rungs 2-3 only run for GitHub hosts and only when rung 1 failed for a reason
sign-in can fix (see shared/git_errors.SIGN_IN_KINDS). The winning method is
cached per repository (host + path) for the process so repeat clones do not
re-probe; reachability depends on the repo, so it is never shared across repos.
Token rungs authenticate over https only, so their result carries `clone_url`.
"""
from __future__ import annotations

import base64
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlsplit

from quodeq.config.github_account import GitHubAccount, load_account
from quodeq.config.github_app import GITHUB_HOST
from quodeq.services.github_gh_cli import GhStatus, gh_status
from quodeq.services.wiring import ProbeResult, pinned_git_config, probe_remote, validate_remote_url
from quodeq.shared.env_resolve import resolve_env
from quodeq.shared.git_errors import SIGN_IN_KINDS, GitFailureKind, NotAGitRepoError
from quodeq.shared.repo import FILE_URL_PREFIX, is_repo_url

_HEADER_KEY = "http.https://github.com/.extraHeader"
_TOKEN_USER = "x-access-token"
_URL_SCHEMES = ("https://", "http://", "ssh://")
_GIT_SUFFIX = ".git"


class AccessMethod(StrEnum):
    """Which rung of the ladder reached the remote."""

    AMBIENT = "ambient"
    QUODEQ = "quodeq"
    GH = "gh"
    LOCAL = "local"  # a file:// repository on this machine: nothing to reach
    NONE = "none"


@dataclass(frozen=True)
class AccessResult:
    """The outcome of walking the ladder for one remote."""

    reachable: bool
    method: AccessMethod
    kind: GitFailureKind
    detail: str
    host: str
    is_github: bool
    env: dict[str, str] | None = field(repr=False)  # the environment to clone with; None = ambient
    clone_url: str | None = None  # None = clone the URL exactly as given


@dataclass(frozen=True)
class AccessDeps:
    """Injectable collaborators; None fields resolve to production ones."""

    probe: Callable[..., ProbeResult] | None = None
    load_account: Callable[[], GitHubAccount | None] | None = None
    gh: Callable[..., GhStatus] | None = None
    env: Mapping[str, str] | None = None
    pin: Callable[[str], list[str]] | None = None


@dataclass(frozen=True)
class _Entry:
    method: AccessMethod
    env: dict[str, str] | None = field(repr=False)
    clone_url: str | None


class AccessCache:
    """Per-repository memory of the method that worked, behind a lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hosts: dict[str, _Entry] = {}
        self._walked: set[str] = set()

    def get(self, key: str) -> _Entry | None:
        """The cached method, env and clone_url for *key*, if any."""
        with self._lock:
            return self._hosts.get(key)

    def put(self, key: str, method: AccessMethod, env: dict[str, str] | None, clone_url: str | None = None) -> None:
        """Remember the method that worked for *key*."""
        with self._lock:
            self._hosts[key] = _Entry(method, env, clone_url)

    def first_walk(self, key: str) -> bool:
        """True the first time *key* is asked about since the last clear."""
        with self._lock:
            fresh = key not in self._walked
            self._walked.add(key)
            return fresh

    def forget(self, key: str) -> None:
        """Drop *key* from the cache."""
        with self._lock:
            self._hosts.pop(key, None)

    def clear(self) -> None:
        """Drop every cached host."""
        with self._lock:
            self._hosts.clear()
            self._walked.clear()


_default_cache = AccessCache()


def _split_remote(url: str) -> tuple[str, str]:
    """``(host, repo path)`` of a remote; the path has no leading/trailing
    slash and no ``.git``. Parsed here rather than through normalize_remote_url,
    whose "numeric tail means port" rule turns ``git@github.com:1password/cli``
    into host ``github.com:1password``."""
    if url.lower().startswith(_URL_SCHEMES):
        parts = urlsplit(url)
        host, path = parts.hostname or "", parts.path
    else:
        user_host, sep, path = url.partition(":")
        if not sep or "@" not in user_host:
            return "", ""
        host = user_host.rsplit("@", 1)[1]
    path = path.strip("/")
    if path.endswith(_GIT_SUFFIX):
        path = path[: -len(_GIT_SUFFIX)]
    return host.lower(), path


def cache_key(url: str) -> str:
    """The per-repository cache key: ``host/path``, else the URL itself."""
    host, path = _split_remote(url)
    return f"{host}/{path}" if host and path else url


def https_form(url: str) -> str:
    """The https clone URL for a remote (scp/ssh forms are mapped); https is unchanged."""
    if url.lower().startswith("https://"):
        return url
    host, path = _split_remote(url)
    return f"https://{host}/{path}{_GIT_SUFFIX}" if host and path else url


def remote_host(url: str) -> str:
    """The host part of any supported remote form, lower-cased."""
    return _split_remote(url)[0]


def is_github_host(host: str) -> bool:
    """True when *host* is github.com (case-insensitive)."""
    return host.lower() == GITHUB_HOST


def access_env(token: str, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """*base* plus a github.com-scoped Authorization header carried in git's
    environment config: not in argv, not in any config file."""
    basic = base64.b64encode(f"{_TOKEN_USER}:{token}".encode()).decode()
    return {
        **resolve_env(base),
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": _HEADER_KEY,
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}",
    }


def _result(reachable: bool, method: AccessMethod, probe: ProbeResult, host: str, env: dict[str, str] | None, clone_url: str | None = None) -> AccessResult:
    return AccessResult(reachable, method, probe.kind, probe.detail, host, is_github_host(host), env, clone_url)


def _url_rejection(url: str) -> GitFailureKind | None:
    """Why the clone would refuse *url* (not a remote URL, cleartext http, a
    private/internal host, a local folder that is not a repository: same
    rules as POST /api/git/probe); None when it passes."""
    try:
        if not is_repo_url(url):
            return GitFailureKind.INVALID_URL
        validate_remote_url(url)
    except NotAGitRepoError:
        return GitFailureKind.NOT_A_GIT_REPO
    except ValueError:
        return GitFailureKind.INVALID_URL
    return None


def _pin(url: str, deps: AccessDeps) -> list[str] | None:
    """The DNS pin for *url* (empty for ssh forms); None when its host does
    not resolve or resolves to an internal address."""
    pin = deps.pin or pinned_git_config
    try:
        return pin(url)
    except ValueError:
        return None


def _try_tokens(url: str, host: str, first: ProbeResult, deps: AccessDeps, pin: list[str]) -> AccessResult:
    probe = deps.probe or probe_remote
    load = deps.load_account or load_account
    gh = deps.gh or gh_status
    https = https_form(url)
    https_pin = pin if https == url else _pin(https, deps)
    if https_pin is None:
        return _result(False, AccessMethod.NONE, first, host, None)
    account = load()
    if account is not None:
        env = access_env(account.token, deps.env)
        if probe(https, env=env, git_config=https_pin).kind is GitFailureKind.OK:
            return _result(True, AccessMethod.QUODEQ, ProbeResult(GitFailureKind.OK), host, env, https)
    status = gh(env=deps.env)
    if status.token:
        env = access_env(status.token, deps.env)
        if probe(https, env=env, git_config=https_pin).kind is GitFailureKind.OK:
            return _result(True, AccessMethod.GH, ProbeResult(GitFailureKind.OK), host, env, https)
    return _result(False, AccessMethod.NONE, first, host, None)


def resolve_access(
    url: str, *, deps: AccessDeps | None = None, cache: AccessCache | None = None,
) -> AccessResult:
    """Walk the ladder for *url*. Never raises."""
    deps = deps or AccessDeps()
    cache = cache or _default_cache
    host = remote_host(url)
    rejection = _url_rejection(url)
    if rejection is not None:
        return AccessResult(False, AccessMethod.NONE, rejection, "", host, False, None)
    if url.startswith(FILE_URL_PREFIX):
        return AccessResult(True, AccessMethod.LOCAL, GitFailureKind.OK, "", "", False, None, url)
    key = cache_key(url)
    cached = cache.get(key)
    if cached is not None:
        return _result(True, cached.method, ProbeResult(GitFailureKind.OK), host, cached.env, cached.clone_url)
    pin = _pin(url, deps)
    if pin is None:
        return _result(False, AccessMethod.NONE, ProbeResult(GitFailureKind.NETWORK), host, None)
    probe = deps.probe or probe_remote
    first = probe(url, env=deps.env, git_config=pin)
    if first.kind is GitFailureKind.OK:
        cache.put(key, AccessMethod.AMBIENT, None)
        return _result(True, AccessMethod.AMBIENT, first, host, None)
    if first.kind not in SIGN_IN_KINDS or not is_github_host(host):
        return _result(False, AccessMethod.NONE, first, host, None)
    result = _try_tokens(url, host, first, deps, pin)
    if result.reachable:
        cache.put(key, result.method, result.env, result.clone_url)
    return result


def cached_access_env(url: str) -> dict[str, str] | None:
    """The env the ladder last reached *url* with; None when uncached or ambient. Never probes."""
    entry = _default_cache.get(cache_key(url))
    return entry.env if entry is not None else None


def refresh_access_env(url: str) -> dict[str, str] | None:
    """The env a refresh (fetch) of the configured *url* should run under.

    The cache is per process, so after an app restart a results repo
    connected through a token rung has no entry. The first refresh then walks
    the ladder once (worst case one probe timeout, about 15 s, once per
    process per URL); later misses mean ambient git and cost nothing.
    """
    key = cache_key(url)
    if _default_cache.get(key) is None and _default_cache.first_walk(key):
        return resolve_access(url).env
    return cached_access_env(url)


def clear_access_cache() -> None:
    """Empty the process-wide cache."""
    _default_cache.clear()


def forget_url(url: str) -> None:
    """Drop the cached method for *url* (after a clone that failed anyway)."""
    _default_cache.forget(cache_key(url))
