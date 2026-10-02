"""The access ladder: how quodeq reaches a git remote, tried in order.

1. Ambient git (SSH agent, credential helper): what `git clone` in a terminal
   would use. Most users never get past this rung.
2. The token quodeq stored (sign-in or paste).
3. The gh CLI's token.
4. Needs sign-in: the honest reason from rung 1, for the UI's access panel.

Rungs 2-3 only run for GitHub hosts and only when rung 1 failed for a reason
sign-in can fix (see shared/git_errors.SIGN_IN_KINDS). The winning method is
cached per host for the process so repeat clones do not re-probe.
"""
from __future__ import annotations

import base64
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from quodeq.config.github_account import GitHubAccount, load_account
from quodeq.config.github_app import GITHUB_HOST
from quodeq.services.github_gh_cli import GhStatus, gh_status
from quodeq.services.wiring import ProbeResult, probe_remote
from quodeq.shared.env_resolve import resolve_env
from quodeq.shared.git_errors import SIGN_IN_KINDS, GitFailureKind
from quodeq.shared.repo import normalize_remote_url

_HEADER_KEY = "http.https://github.com/.extraHeader"
_TOKEN_USER = "x-access-token"


class AccessMethod(StrEnum):
    """Which rung of the ladder reached the remote."""

    AMBIENT = "ambient"
    QUODEQ = "quodeq"
    GH = "gh"
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
    env: dict[str, str] | None  # the environment to clone with; None = ambient


@dataclass(frozen=True)
class AccessDeps:
    """Injectable collaborators; None fields resolve to production ones."""

    probe: Callable[..., ProbeResult] | None = None
    load_account: Callable[[], GitHubAccount | None] | None = None
    gh: Callable[..., GhStatus] | None = None
    env: Mapping[str, str] | None = None


class AccessCache:
    """Per-host memory of the method that worked, behind a lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hosts: dict[str, tuple[AccessMethod, dict[str, str] | None]] = {}

    def get(self, host: str) -> tuple[AccessMethod, dict[str, str] | None] | None:
        """The cached method and env for *host*, if any."""
        with self._lock:
            return self._hosts.get(host)

    def put(self, host: str, method: AccessMethod, env: dict[str, str] | None) -> None:
        """Remember the method that worked for *host*."""
        with self._lock:
            self._hosts[host] = (method, env)

    def forget(self, host: str) -> None:
        """Drop *host* from the cache."""
        with self._lock:
            self._hosts.pop(host, None)

    def clear(self) -> None:
        """Drop every cached host."""
        with self._lock:
            self._hosts.clear()


_default_cache = AccessCache()


def remote_host(url: str) -> str:
    """The host part of any supported remote form, lower-cased."""
    normalized = normalize_remote_url(url) or ""
    return normalized.split("/", 1)[0].lower()


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


def _result(reachable: bool, method: AccessMethod, probe: ProbeResult, host: str, env: dict[str, str] | None) -> AccessResult:
    return AccessResult(reachable, method, probe.kind, probe.detail, host, is_github_host(host), env)


def _try_tokens(url: str, host: str, first: ProbeResult, deps: AccessDeps) -> AccessResult:
    probe = deps.probe or probe_remote
    load = deps.load_account or load_account
    gh = deps.gh or gh_status
    account = load()
    if account is not None:
        env = access_env(account.token, deps.env)
        if probe(url, env=env).kind is GitFailureKind.OK:
            return _result(True, AccessMethod.QUODEQ, ProbeResult(GitFailureKind.OK), host, env)
    status = gh(env=deps.env)
    if status.token:
        env = access_env(status.token, deps.env)
        if probe(url, env=env).kind is GitFailureKind.OK:
            return _result(True, AccessMethod.GH, ProbeResult(GitFailureKind.OK), host, env)
    return _result(False, AccessMethod.NONE, first, host, None)


def resolve_access(
    url: str, *, deps: AccessDeps | None = None, cache: AccessCache | None = None,
) -> AccessResult:
    """Walk the ladder for *url*. Never raises."""
    deps = deps or AccessDeps()
    cache = cache or _default_cache
    host = remote_host(url)
    cached = cache.get(host)
    if cached is not None:
        method, env = cached
        return _result(True, method, ProbeResult(GitFailureKind.OK), host, env)
    probe = deps.probe or probe_remote
    first = probe(url, env=deps.env)
    if first.kind is GitFailureKind.OK:
        cache.put(host, AccessMethod.AMBIENT, None)
        return _result(True, AccessMethod.AMBIENT, first, host, None)
    if first.kind not in SIGN_IN_KINDS or not is_github_host(host):
        return _result(False, AccessMethod.NONE, first, host, None)
    result = _try_tokens(url, host, first, deps)
    if result.reachable:
        cache.put(host, result.method, result.env)
    return result


def clear_access_cache() -> None:
    """Empty the process-wide per-host cache."""
    _default_cache.clear()


def forget_host(url: str) -> None:
    """Drop the cached method for *url*'s host (after a clone that failed anyway)."""
    _default_cache.forget(remote_host(url))
